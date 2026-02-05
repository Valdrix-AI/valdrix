
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.remediation import RemediationHandler
from app.models.background_job import BackgroundJob

@pytest.mark.asyncio
async def test_execute_missing_tenant(db):
    handler = RemediationHandler()
    job = BackgroundJob(tenant_id=None)
    
    with pytest.raises(ValueError, match="tenant_id required"):
        await handler.execute(job, db)

@pytest.mark.asyncio
async def test_execute_targeted_remediation(db):
    handler = RemediationHandler()
    request_id = uuid4()
    job = BackgroundJob(tenant_id=uuid4(), payload={"request_id": str(request_id)})
    
    mock_result = MagicMock()
    mock_result.id = request_id
    mock_result.status.value = "completed"
    
    with patch("app.modules.optimization.domain.remediation.RemediationService") as MockService:
        service = MockService.return_value
        service.execute = AsyncMock(return_value=mock_result)
        
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["mode"] == "targeted"
        assert result["request_id"] == str(request_id)
        
        service.execute.assert_awaited_with(request_id, job.tenant_id)

@pytest.mark.asyncio
async def test_execute_autonomous_no_connection(db):
    handler = RemediationHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    
    # Mock database returning no connection
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_res)
    
    result = await handler.execute(job, db)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_aws_connection"

@pytest.mark.asyncio
async def test_execute_autonomous_success(db):
    handler = RemediationHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    
    # Mock AWS Connection
    mock_conn = MagicMock()
    mock_conn.region = "us-east-1"
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_conn
    db.execute = AsyncMock(return_value=mock_res)
    
    with patch("app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter") as MockAdapter, \
         patch("app.shared.remediation.autonomous.AutonomousRemediationEngine") as MockEngine:
        
        adapter = MockAdapter.return_value
        adapter.get_credentials = AsyncMock(return_value={"key": "val"})
        
        engine = MockEngine.return_value
        engine.run_autonomous_sweep = AsyncMock(return_value={
            "mode": "autonomous",
            "scanned": 10,
            "auto_executed": 2
        })
        
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["scanned"] == 10
        assert result["auto_executed"] == 2
