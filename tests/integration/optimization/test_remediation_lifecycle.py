import pytest
import boto3
import json
from moto import mock_aws
from uuid import uuid4
from sqlalchemy import select
from httpx import AsyncClient

from app.models.tenant import Tenant, User, UserRole
from app.models.aws_connection import AWSConnection
from app.models.remediation import RemediationRequest, RemediationStatus
from app.shared.core.pricing import PricingTier
from app.shared.db.session import get_db
from tests.utils import create_test_token

@pytest.fixture(autouse=True)
async def cleanup_overrides():
    """Cleanup dependency overrides after each test."""
    from app.main import app
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    import os
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

@pytest.fixture
async def setup_opt_data(db):
    """Setup a Pro tier tenant with an active AWS connection."""
    tenant = Tenant(id=uuid4(), name="Optimization Corp", plan=PricingTier.PRO.value)
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="ops@optcorp.com",
        role=UserRole.ADMIN
    )
    
    conn = AWSConnection(
        id=uuid4(),
        tenant_id=tenant.id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ValdrixTestRole",
        region="us-east-1",
        status="active"
    )
    
    db.add(tenant)
    db.add(user)
    db.add(conn)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)
    
    token = create_test_token(user.id, user.email)
    return {"tenant": tenant, "user": user, "token": token, "connection": conn}

class AsyncPaginatorWrapper:
    def __init__(self, sync_paginator):
        self._sync_paginator = sync_paginator

    def paginate(self, *args, **kwargs):
        self._iter = iter(self._sync_paginator.paginate(*args, **kwargs))
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

class AsyncClientWrapper:
    """Wrapper to make boto3 sync clients behave like aioboto3 async clients."""
    def __init__(self, sync_client):
        self._sync_client = sync_client
    
    def __getattr__(self, name):
        attr = getattr(self._sync_client, name)
        if name == "get_paginator":
            def get_paginator_wrapper(*args, **kwargs):
                print(f"DEBUG: get_paginator({args}, {kwargs})")
                return AsyncPaginatorWrapper(attr(*args, **kwargs))
            return get_paginator_wrapper
            
        if callable(attr):
            async def wrapper(*args, **kwargs):
                print(f"DEBUG: Calling {name}({args}, {kwargs})")
                # Execute directly in main thread for moto compatibility
                res = attr(*args, **kwargs)
                print(f"DEBUG: {name} returned")
                return res
            return wrapper
        return attr

    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass

@pytest.mark.anyio
async def test_remediation_lifecycle_full(ac: AsyncClient, setup_opt_data, db, aws_credentials):
    """Full remediation lifecycle integration test."""
    with mock_aws():
        # Setup mock AWS
        ec2 = boto3.client("ec2", region_name="us-east-1")
        run_instances = ec2.run_instances(
            ImageId="ami-12345678",
            MaxCount=1,
            MinCount=1,
            InstanceType="t2.micro"
        )
        instance_id = run_instances["Instances"][0]["InstanceId"]
        
        headers = {"Authorization": f"Bearer {setup_opt_data['token']}"}
        
        import aioboto3
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        
        def mock_client(self, service_name, **kwargs):
            return AsyncClientWrapper(boto3.client(service_name, region_name="us-east-1"))
        
        async def mock_get_credentials(self):
            return {"AccessKeyId": "testing", "SecretAccessKey": "testing", "SessionToken": "testing"}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(aioboto3.Session, "client", mock_client)
            mp.setattr(MultiTenantAWSAdapter, "get_credentials", mock_get_credentials)
            
            # 1. Run Scan
            response = await ac.get("/api/v1/zombies?region=us-east-1", headers=headers)
            assert response.status_code == 200
            
            # 2. Request Remediation
            req_payload = {
                "resource_id": instance_id,
                "resource_type": "EC2 Instance",
                "action": "terminate_instance",
                "estimated_savings": 15.50
            }
            response = await ac.post("/api/v1/zombies/request", json=req_payload, headers=headers)
            assert response.status_code == 200
            request_id = response.json()["request_id"]
            
            # 3. Approve
            response = await ac.post(f"/api/v1/zombies/approve/{request_id}", json={"notes": "test"}, headers=headers)
            assert response.status_code == 200
            
            # 4. Execute
            response = await ac.post(f"/api/v1/zombies/execute/{request_id}?bypass_grace_period=true", headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "completed"
            
            # 5. Verify In Mock AWS
            desc = ec2.describe_instances(InstanceIds=[instance_id])
            assert desc["Reservations"][0]["Instances"][0]["State"]["Name"] in ["shutting-down", "terminated"]
            
            # 6. Verify DB
            from uuid import UUID
            result = await db.execute(select(RemediationRequest).where(RemediationRequest.id == UUID(request_id)))
            rem = result.scalar_one()
            assert rem.status == RemediationStatus.COMPLETED
