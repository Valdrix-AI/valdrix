import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.acceptance import (
    AcceptanceSuiteCaptureHandler,
)
from app.modules.governance.domain.security.audit_log import AuditEventType


@pytest.mark.asyncio
async def test_acceptance_suite_capture_handler_logs_kpis_and_integrations():
    db = MagicMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=MagicMock(plan="pro"))

    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = uuid4()
    job.payload = {}

    handler = AcceptanceSuiteCaptureHandler()

    dummy_kpis = MagicMock()
    dummy_kpis.model_dump.return_value = {"tier": "pro", "metrics": []}

    dummy_leadership = MagicMock()
    dummy_leadership.model_dump.return_value = {
        "tier": "pro",
        "window": {},
        "totals": {},
    }

    with (
        patch(
            "app.modules.reporting.api.v1.costs._compute_acceptance_kpis_payload",
            new_callable=AsyncMock,
            return_value=dummy_kpis,
        ),
        patch(
            "app.modules.reporting.domain.leadership_kpis.LeadershipKpiService.compute",
            new_callable=AsyncMock,
            return_value=dummy_leadership,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_slack_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_jira_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_teams_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_workflow_dispatchers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.AuditLogger"
        ) as mock_audit_cls,
    ):
        mock_audit = MagicMock()
        mock_audit.log = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["acceptance_kpis_captured"] is True
        assert result["integrations"]["failed"] == 0

        event_types = [
            call.kwargs["event_type"] for call in mock_audit.log.call_args_list
        ]
        assert AuditEventType.ACCEPTANCE_KPIS_CAPTURED in event_types
        assert AuditEventType.INTEGRATION_TEST_SLACK in event_types
        assert AuditEventType.INTEGRATION_TEST_JIRA in event_types
        assert AuditEventType.INTEGRATION_TEST_TEAMS in event_types
        assert AuditEventType.INTEGRATION_TEST_WORKFLOW in event_types
        assert AuditEventType.INTEGRATION_TEST_SUITE in event_types


@pytest.mark.asyncio
async def test_acceptance_suite_capture_handler_handles_kpi_failure():
    db = MagicMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=MagicMock(plan="starter"))

    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = uuid4()
    job.payload = {}

    handler = AcceptanceSuiteCaptureHandler()

    with (
        patch(
            "app.modules.reporting.api.v1.costs._compute_acceptance_kpis_payload",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_slack_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_jira_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_teams_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_workflow_dispatchers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.AuditLogger"
        ) as mock_audit_cls,
    ):
        mock_audit = MagicMock()
        mock_audit.log = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["acceptance_kpis_captured"] is False

        # Ensure KPI event was recorded as failure.
        first_call = mock_audit.log.call_args_list[0]
        assert (
            first_call.kwargs["event_type"] == AuditEventType.ACCEPTANCE_KPIS_CAPTURED
        )
        assert first_call.kwargs["success"] is False


@pytest.mark.asyncio
async def test_acceptance_suite_capture_handler_captures_close_package_when_requested():
    db = MagicMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=MagicMock(plan="pro"))

    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = uuid4()
    job.payload = {"capture_close_package": True}

    handler = AcceptanceSuiteCaptureHandler()

    dummy_kpis = MagicMock()
    dummy_kpis.model_dump.return_value = {"tier": "pro", "metrics": []}

    dummy_leadership = MagicMock()
    dummy_leadership.model_dump.return_value = {
        "tier": "pro",
        "window": {},
        "totals": {},
    }

    dummy_close_package = {
        "close_status": "ready",
        "integrity_hash": "abc123",
        "period": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
        "lifecycle": {"total_records": 1},
        "csv": "section,key,value\nmeta,tenant_id,x\n",
    }

    with (
        patch(
            "app.modules.reporting.api.v1.costs._compute_acceptance_kpis_payload",
            new_callable=AsyncMock,
            return_value=dummy_kpis,
        ),
        patch(
            "app.modules.reporting.domain.leadership_kpis.LeadershipKpiService.compute",
            new_callable=AsyncMock,
            return_value=dummy_leadership,
        ),
        patch(
            "app.modules.reporting.domain.reconciliation.CostReconciliationService.generate_close_package",
            new_callable=AsyncMock,
            return_value=dummy_close_package,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_slack_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_jira_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_teams_service",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.get_tenant_workflow_dispatchers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.acceptance.AuditLogger"
        ) as mock_audit_cls,
    ):
        mock_audit = MagicMock()
        mock_audit.log = AsyncMock()
        mock_audit_cls.return_value = mock_audit

        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["close_package_capture_requested"] is True
        assert result["close_package_captured"] is True

        event_types = [
            call.kwargs["event_type"] for call in mock_audit.log.call_args_list
        ]
        assert AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED in event_types

        close_calls = [
            call
            for call in mock_audit.log.call_args_list
            if call.kwargs["event_type"]
            == AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED
        ]
        assert len(close_calls) == 1
        captured_payload = close_calls[0].kwargs["details"]["payload"]
        assert isinstance(captured_payload, dict)
        assert "csv" not in captured_payload
