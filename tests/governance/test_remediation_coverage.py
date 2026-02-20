import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from decimal import Decimal
from app.modules.optimization.domain.remediation import RemediationService
from app.models.remediation import RemediationRequest, RemediationStatus, RemediationAction
from app.models.tenant import Tenant
from botocore.exceptions import ClientError

@pytest_asyncio.fixture
async def test_tenant(db):
    tenant = Tenant(id=uuid4(), name="Test Tenant", plan="pro", is_deleted=False)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant

@pytest_asyncio.fixture
async def remediation_service(db):
    return RemediationService(db)

async def create_request(db, tenant_id, resource_id, action):
    request = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        resource_id=resource_id,
        resource_type="ec2_instance",
        provider="aws",
        region="us-east-1",
        action=action,
        status=RemediationStatus.APPROVED,
        estimated_monthly_savings=Decimal("100.00"),
        requested_by_user_id=uuid4()
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request

@pytest.mark.asyncio
async def test_execute_ec2_stop(db, remediation_service, test_tenant):
    """Test EC2 STOP_INSTANCE via execute API."""
    resource_id = "i-12345678"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.STOP_INSTANCE)
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_ec2 = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.COMPLETED
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=[resource_id])

@pytest.mark.asyncio
async def test_execute_rds_stop(db, remediation_service, test_tenant):
    """Test RDS STOP_RDS_INSTANCE via execute API."""
    resource_id = "db-123"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.STOP_RDS_INSTANCE)
    request.resource_type = "rds_instance"
    await db.commit()
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_rds = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_rds
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.COMPLETED
        mock_rds.stop_db_instance.assert_called_once_with(DBInstanceIdentifier=resource_id)

@pytest.mark.asyncio
async def test_execute_s3_delete(db, remediation_service, test_tenant):
    """Test S3 DELETE_S3_BUCKET via execute API."""
    resource_id = "bucket-123"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.DELETE_S3_BUCKET)
    request.resource_type = "s3_bucket"
    await db.commit()
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_s3 = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_s3
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.COMPLETED
        mock_s3.delete_bucket.assert_called_once_with(Bucket=resource_id)

@pytest.mark.asyncio
async def test_execute_ecr_delete(db, remediation_service, test_tenant):
    """Test ECR DELETE_ECR_IMAGE via execute API."""
    resource_id = "repo@sha256:123"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.DELETE_ECR_IMAGE)
    request.resource_type = "ecr_image"
    await db.commit()
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_ecr = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_ecr
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.COMPLETED
        mock_ecr.batch_delete_image.assert_called_once()

@pytest.mark.asyncio
async def test_execute_failure_logging(db, remediation_service, test_tenant):
    """Test error handling and logging when execution fails."""
    resource_id = "i-fail"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.TERMINATE_INSTANCE)
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_ec2 = AsyncMock()
        mock_ec2.terminate_instances.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "Access Denied"}},
            "TerminateInstances"
        )
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.FAILED
        assert "Access Denied" in request.execution_error

@pytest.mark.asyncio
async def test_execute_rds_backup_integration(db, remediation_service, test_tenant):
    """Test RDS deletion with backup enabled."""
    resource_id = "db-backup"
    request = await create_request(db, test_tenant.id, resource_id, RemediationAction.DELETE_RDS_INSTANCE)
    request.resource_type = "rds_instance"
    request.create_backup = True
    await db.commit()
    
    with patch("app.modules.optimization.domain.actions.aws.base.BaseAWSAction._get_client") as mock_get_client:
        mock_rds = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_rds
        
        await remediation_service.execute(request.id, test_tenant.id, bypass_grace_period=True)
        
        await db.refresh(request)
        assert request.status == RemediationStatus.COMPLETED
        assert request.backup_resource_id is not None
        assert request.backup_resource_id.startswith("valdrix-backup-db-backup-")
        mock_rds.create_db_snapshot.assert_called_once()
        mock_rds.delete_db_instance.assert_called_once()
