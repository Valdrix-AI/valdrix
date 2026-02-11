import pytest
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
from app.modules.optimization.domain.remediation import RemediationService, RemediationAction
from app.models.remediation import RemediationStatus

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # default result for safety checks
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("0")
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    db.commit = AsyncMock()
    return db

@pytest.fixture
def remediation_service(mock_db):
    return RemediationService(mock_db)

class AsyncContextManagerMock:
    def __init__(self, obj):
        self.obj = obj
    async def __aenter__(self):
        return self.obj
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.mark.asyncio
async def test_execute_remediation_error_handling(remediation_service, mock_db):
    """Test error handling in execute."""
    remediation_id = uuid.uuid4()
    mock_remediation = MagicMock()
    mock_remediation.id = remediation_id
    mock_remediation.status = RemediationStatus.APPROVED
    mock_remediation.resource_id = "i-123"
    mock_remediation.action = RemediationAction.STOP_INSTANCE
    mock_remediation.tenant_id = uuid.uuid4()
    mock_remediation.reviewed_by_user_id = uuid.uuid4()
    mock_remediation.create_backup = False
    mock_remediation.estimated_monthly_savings = Decimal("10.0")
    mock_remediation.execution_error = None
    
    # Mock DB results for BOTH the main query and safety checks
    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = mock_remediation
    
    mock_result_safety = MagicMock()
    mock_result_safety.scalar.return_value = Decimal("0")
    mock_result_safety.scalar_one_or_none.return_value = None # No settings
    
    # Provide enough results for all calls (main query + 3 safety checks)
    mock_db.execute.side_effect = [mock_result_main, mock_result_safety, mock_result_safety, mock_result_safety, mock_result_safety]
    
    mock_ec2 = AsyncMock()
    mock_ec2.stop_instances.side_effect = Exception("Execution failed")
    
    async def mock_get_client_func(service_name):
        return AsyncContextManagerMock(mock_ec2)
    
    remediation_service._get_client = mock_get_client_func
    
    await remediation_service.execute(remediation_id, mock_remediation.tenant_id, bypass_grace_period=True)
    
    assert mock_remediation.status == RemediationStatus.FAILED
    assert "Execution failed" in mock_remediation.execution_error

@pytest.mark.asyncio
async def test_remediation_with_backup_and_verify(remediation_service, mock_db):
    """Test remediation flow including backup steps."""
    remediation_id = uuid.uuid4()
    mock_remediation = MagicMock()
    mock_remediation.id = remediation_id
    mock_remediation.status = RemediationStatus.APPROVED
    mock_remediation.resource_id = "vol-123"
    mock_remediation.action = RemediationAction.DELETE_VOLUME
    mock_remediation.tenant_id = uuid.uuid4()
    mock_remediation.reviewed_by_user_id = uuid.uuid4()
    mock_remediation.create_backup = True
    mock_remediation.backup_retention_days = 7
    mock_remediation.estimated_monthly_savings = Decimal("10.0")
    mock_remediation.execution_error = None
    
    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = mock_remediation
    mock_result_safety = MagicMock()
    mock_result_safety.scalar.return_value = Decimal("0")
    mock_result_safety.scalar_one_or_none.return_value = None
    
    # Provide enough results
    mock_db.execute.side_effect = [mock_result_main, mock_result_safety, mock_result_safety, mock_result_safety, mock_result_safety]
    
    mock_ec2 = AsyncMock()
    mock_ec2.create_snapshot.return_value = {"SnapshotId": "snap-123"}
    mock_ec2.delete_volume.return_value = {}
    
    async def mock_get_client_func(service_name):
        return AsyncContextManagerMock(mock_ec2)
    
    remediation_service._get_client = mock_get_client_func
    
    result = await remediation_service.execute(remediation_id, mock_remediation.tenant_id, bypass_grace_period=True)
    assert result.status == RemediationStatus.COMPLETED
    mock_ec2.create_snapshot.assert_called()
    mock_ec2.delete_volume.assert_called()
