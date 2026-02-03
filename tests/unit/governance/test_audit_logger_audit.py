import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4, UUID
from app.modules.governance.domain.security.audit_log import AuditLogger, AuditEventType, AuditLog

@pytest.fixture
def mock_db():
    mock = MagicMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock()
    return mock

@pytest.mark.asyncio
async def test_audit_logger_initialization(mock_db):
    tenant_id_str = str(uuid4())
    logger = AuditLogger(mock_db, tenant_id_str)
    assert isinstance(logger.tenant_id, UUID)
    assert logger.tenant_id == UUID(tenant_id_str)
    assert logger.correlation_id is not None

@pytest.mark.asyncio
async def test_log_creation_success(mock_db):
    tenant_id = uuid4()
    logger = AuditLogger(mock_db, tenant_id)
    
    actor_id = uuid4()
    
    entry = await logger.log(
        event_type=AuditEventType.REMEDIATION_EXECUTED,
        actor_id=actor_id,
        resource_type="AWS::EC2::Volume",
        resource_id="vol-test",
        details={"size": 100},
        success=True
    )
    
    assert isinstance(entry, AuditLog)
    assert entry.tenant_id == tenant_id
    assert entry.event_type == AuditEventType.REMEDIATION_EXECUTED.value
    assert entry.actor_id == actor_id
    assert entry.details == {"size": 100}
    assert entry.success is True
    
    mock_db.add.assert_called_once_with(entry)
    mock_db.flush.assert_awaited_once()

@pytest.mark.asyncio
async def test_sensitive_data_masking(mock_db):
    tenant_id = uuid4()
    logger = AuditLogger(mock_db, tenant_id)
    
    sensitive_details = {
        "user_password": "supersecretpassword",
        "api_key": "AKIA12345678",
        "config": {
            "db_password": "dbpassword",
            "safe_field": "safe"
        },
        "list_data": [
            {"token": "xyz"},
            "plain_text"
        ]
    }
    
    entry = await logger.log(
        event_type=AuditEventType.SYSTEM_MAINTENANCE,
        details=sensitive_details
    )
    
    masked = entry.details
    assert masked["user_password"] == "***REDACTED***"
    assert masked["api_key"] == "***REDACTED***"
    assert masked["config"]["db_password"] == "***REDACTED***"
    assert masked["config"]["safe_field"] == "safe"
    assert masked["list_data"][0]["token"] == "***REDACTED***"
    assert masked["list_data"][1] == "plain_text"

@pytest.mark.asyncio
async def test_log_error_tracking(mock_db):
    tenant_id = uuid4()
    logger = AuditLogger(mock_db, tenant_id)
    
    entry = await logger.log(
        event_type=AuditEventType.REMEDIATION_FAILED,
        success=False,
        error_message="Permission denied"
    )
    
    assert entry.success is False
    assert entry.error_message == "Permission denied"
