
import pytest
from httpx import AsyncClient
from datetime import date
from uuid import uuid4
from decimal import Decimal
from app.models.cloud import CloudAccount, CostRecord
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.db.session import get_db
from app.main import app

@pytest.fixture
def mock_auth_user():
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        email="test@valdrix.ai",
        tenant_id=tenant_id,
        role="member",
        permissions=["read", "write"],
        tier="enterprise"
    )
    return user

@pytest.mark.asyncio
async def test_cost_aggregation_and_filtering(ac: AsyncClient, db, mock_auth_user):
    # Setup: Override Auth & DB Dependency
    app.dependency_overrides[get_current_user] = lambda: mock_auth_user
    app.dependency_overrides[get_db] = lambda: db
    
    try:
        tenant_id = mock_auth_user.tenant_id
        
        # 0. Create Tenant (REQUIRED for RLS/Foreign Keys)
        from sqlalchemy import text
        await db.execute(text(f"INSERT INTO tenants (id, name, plan) VALUES ('{tenant_id}', 'Test Tenant', 'enterprise') ON CONFLICT DO NOTHING"))
        await db.commit()
        
        # 1. AWS Connection & Account
        aws_id = uuid4()
        aws_cloud = CloudAccount(
            id=aws_id,
            tenant_id=tenant_id,
            provider="aws",
            name="AWS Prod",
            is_active=True
        )

        db.add(aws_cloud)

        # 2. Azure Account
        azure_id = uuid4()
        azure_cloud = CloudAccount(
            id=azure_id,
            tenant_id=tenant_id,
            provider="azure",
            name="Azure Dev",
            is_active=True
        )

        db.add(azure_cloud)

        # 3. Insert Cost Records
        today = date.today()
        
        # AWS Cost: $100 EC2
        db.add(CostRecord(
            tenant_id=tenant_id,
            account_id=aws_id,
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage",
            cost_usd=Decimal("100.00"),
            currency="USD",
            recorded_at=today
        ))
        
        # Azure Cost: $50 SQL
        db.add(CostRecord(
            tenant_id=tenant_id,
            account_id=azure_id,
            service="AzureSQL",
            region="eastus",
            usage_type="Database",
            cost_usd=Decimal("50.00"),
            currency="USD",
            recorded_at=today
        ))
        
        await db.commit()

        # Test 1: Aggregated Total (All Providers)
        resp = await ac.get(
            f"/api/v1/costs?start_date={today}&end_date={today}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 150.0
        assert len(data["breakdown"]) == 2

        # Test 2: Filter by AWS
        resp_aws = await ac.get(
            f"/api/v1/costs?start_date={today}&end_date={today}&provider=aws"
        )
        data_aws = resp_aws.json()
        assert data_aws["total_cost"] == 100.0
        assert len(data_aws["breakdown"]) == 1
        assert data_aws["breakdown"][0]["service"] == "AmazonEC2"

        # Test 3: Filter by Azure
        resp_azure = await ac.get(
            f"/api/v1/costs?start_date={today}&end_date={today}&provider=azure"
        )
        data_azure = resp_azure.json()
        assert data_azure["total_cost"] == 50.0
        assert len(data_azure["breakdown"]) == 1
        assert data_azure["breakdown"][0]["service"] == "AzureSQL"

    finally:
        # Cleanup Override
        app.dependency_overrides = {}
