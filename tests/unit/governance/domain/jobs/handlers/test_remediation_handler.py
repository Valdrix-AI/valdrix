import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.remediation import RemediationHandler
from app.models.background_job import BackgroundJob
from app.models.remediation import RemediationStatus


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

    remediation_request = MagicMock()
    remediation_request.id = request_id
    remediation_request.tenant_id = job.tenant_id
    remediation_request.provider = "aws"
    remediation_request.region = "us-east-1"
    remediation_request.status = RemediationStatus.APPROVED
    remediation_request.connection_id = None
    remediation_request.scheduled_execution_at = None

    mock_remediation_res = MagicMock()
    mock_remediation_res.scalar_one_or_none.return_value = remediation_request

    db.execute = AsyncMock(return_value=mock_remediation_res)

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as MockService:
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

    with patch(
        "app.shared.remediation.autonomous.AutonomousRemediationEngine"
    ) as MockEngine:
        engine = MockEngine.return_value
        engine.run_autonomous_sweep = AsyncMock(
            return_value={
                "mode": "dry_run",
                "scanned": 0,
                "auto_executed": 0,
                "error": "no_connections_found",
            }
        )
        result = await handler.execute(job, db)

    assert result["status"] == "skipped"
    assert result["reason"] == "no_connections_found"


@pytest.mark.asyncio
async def test_execute_autonomous_success(db):
    handler = RemediationHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})

    with patch(
        "app.shared.remediation.autonomous.AutonomousRemediationEngine"
    ) as MockEngine:
        engine = MockEngine.return_value
        engine.run_autonomous_sweep = AsyncMock(
            return_value={"mode": "autonomous", "scanned": 10, "auto_executed": 2}
        )

        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["scanned"] == 10
        assert result["auto_executed"] == 2


@pytest.mark.asyncio
async def test_execute_targeted_remediation_failed_maps_reason(db):
    handler = RemediationHandler()
    request_id = uuid4()
    job = BackgroundJob(tenant_id=uuid4(), payload={"request_id": str(request_id)})

    mock_result = MagicMock()
    mock_result.id = request_id
    mock_result.status.value = "failed"
    mock_result.execution_error = (
        "[aws_connection_missing] No AWS connection found for this tenant (Status: 400)"
    )

    remediation_request = MagicMock()
    remediation_request.id = request_id
    remediation_request.tenant_id = job.tenant_id
    remediation_request.provider = "aws"
    remediation_request.region = "us-east-1"
    remediation_request.status = RemediationStatus.APPROVED
    remediation_request.connection_id = None
    remediation_request.scheduled_execution_at = None

    mock_remediation_res = MagicMock()
    mock_remediation_res.scalar_one_or_none.return_value = remediation_request

    db.execute = AsyncMock(return_value=mock_remediation_res)

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as MockService:
        service = MockService.return_value
        service.execute = AsyncMock(return_value=mock_result)

        result = await handler.execute(job, db)

    assert result["status"] == "failed"
    assert result["mode"] == "targeted"
    assert result["request_id"] == str(request_id)
    assert result["remediation_status"] == "failed"
    assert result["reason"] == "aws_connection_missing"
    assert result["status_code"] == 400


@pytest.mark.asyncio
async def test_execute_targeted_remediation_non_aws_provider_supported(db):
    handler = RemediationHandler()
    request_id = uuid4()
    tenant_id = uuid4()
    job = BackgroundJob(tenant_id=tenant_id, payload={"request_id": str(request_id)})

    mock_result = MagicMock()
    mock_result.id = request_id
    mock_result.status.value = "completed"

    remediation_request = MagicMock()
    remediation_request.id = request_id
    remediation_request.tenant_id = tenant_id
    remediation_request.provider = "license"
    remediation_request.region = "global"
    remediation_request.status = RemediationStatus.APPROVED
    remediation_request.connection_id = None
    remediation_request.scheduled_execution_at = None

    mock_remediation_res = MagicMock()
    mock_remediation_res.scalar_one_or_none.return_value = remediation_request
    db.execute = AsyncMock(return_value=mock_remediation_res)

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as MockService:
        service = MockService.return_value
        service.execute = AsyncMock(return_value=mock_result)

        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["mode"] == "targeted"
    assert result["request_id"] == str(request_id)
    service.execute.assert_awaited_once_with(request_id, tenant_id)
