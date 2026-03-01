from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers import acceptance as acceptance_handler
from app.modules.governance.domain.security.audit_log import AuditEventType
from app.shared.core.pricing import FeatureFlag, PricingTier


def _db(plan: str = "pro") -> MagicMock:
    db = MagicMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=SimpleNamespace(plan=plan))
    return db


def _job(payload: dict[str, object] | None = None) -> MagicMock:
    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = uuid4()
    job.payload = payload or {}
    return job


def _model_payload(data: dict[str, object]) -> MagicMock:
    payload = MagicMock()
    payload.model_dump.return_value = data
    return payload


def _audit_event_calls(audit: MagicMock, event_type: AuditEventType) -> list[object]:
    return [
        call
        for call in audit.log.call_args_list
        if call.kwargs.get("event_type") == event_type
    ]


@contextmanager
def _patched_acceptance_environment(
    *,
    feature_flags: dict[FeatureFlag, bool] | None = None,
    kpi_payload: object | None = None,
    kpi_side_effect: Exception | None = None,
    leadership_payload: object | None = None,
    quarterly_payload: object | None = None,
    quarterly_side_effect: Exception | None = None,
    close_package_payload: dict[str, object] | None = None,
    close_package_side_effect: Exception | None = None,
    slack_service: object | None = None,
    jira_service: object | None = None,
    teams_service: object | None = None,
    workflow_dispatchers: list[object] | None = None,
):
    flags = feature_flags or {}

    def _feature_enabled(_tier: PricingTier, flag: FeatureFlag) -> bool:
        return flags.get(flag, True)

    with ExitStack() as stack:
        kpi_patch = stack.enter_context(
            patch(
                "app.modules.reporting.api.v1.costs._compute_acceptance_kpis_payload",
                new_callable=AsyncMock,
            )
        )
        if kpi_side_effect is not None:
            kpi_patch.side_effect = kpi_side_effect
        else:
            kpi_patch.return_value = kpi_payload or _model_payload({"metrics": []})

        leadership_patch = stack.enter_context(
            patch(
                "app.modules.reporting.domain.leadership_kpis.LeadershipKpiService.compute",
                new_callable=AsyncMock,
                return_value=leadership_payload or _model_payload({"totals": {}}),
            )
        )
        quarterly_patch = stack.enter_context(
            patch(
                "app.modules.reporting.domain.commercial_reports.CommercialProofReportService.quarterly_report",
                new_callable=AsyncMock,
            )
        )
        if quarterly_side_effect is not None:
            quarterly_patch.side_effect = quarterly_side_effect
        else:
            quarterly_patch.return_value = quarterly_payload

        close_patch = stack.enter_context(
            patch(
                "app.modules.reporting.domain.reconciliation.CostReconciliationService.generate_close_package",
                new_callable=AsyncMock,
            )
        )
        if close_package_side_effect is not None:
            close_patch.side_effect = close_package_side_effect
        else:
            close_patch.return_value = close_package_payload or {
                "close_status": "ready",
                "integrity_hash": "hash",
            }

        stack.enter_context(
            patch.object(
                acceptance_handler,
                "get_tenant_slack_service",
                new=AsyncMock(return_value=slack_service),
            )
        )
        stack.enter_context(
            patch.object(
                acceptance_handler,
                "get_tenant_jira_service",
                new=AsyncMock(return_value=jira_service),
            )
        )
        stack.enter_context(
            patch.object(
                acceptance_handler,
                "get_tenant_teams_service",
                new=AsyncMock(return_value=teams_service),
            )
        )
        stack.enter_context(
            patch.object(
                acceptance_handler,
                "get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=workflow_dispatchers or []),
            )
        )
        stack.enter_context(
            patch.object(acceptance_handler, "is_feature_enabled", side_effect=_feature_enabled)
        )
        logger_mock = stack.enter_context(patch.object(acceptance_handler, "logger"))
        audit_cls = stack.enter_context(patch.object(acceptance_handler, "AuditLogger"))
        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        yield {
            "audit": audit,
            "logger": logger_mock,
            "kpi_compute": kpi_patch,
            "leadership_compute": leadership_patch,
            "quarterly_report": quarterly_patch,
            "close_package": close_patch,
        }


def test_acceptance_handler_helpers_cover_edge_cases() -> None:
    tenant_id = uuid4()
    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = tenant_id
    assert acceptance_handler._require_tenant_id(job) == tenant_id

    missing = MagicMock(spec=BackgroundJob)
    missing.tenant_id = None
    with pytest.raises(ValueError, match="tenant_id required"):
        acceptance_handler._require_tenant_id(missing)

    assert acceptance_handler._iso_date("2026-02-01") == date(2026, 2, 1)
    assert acceptance_handler._iso_date(date(2026, 2, 2)) == date(2026, 2, 2)
    with pytest.raises(ValueError, match="Expected ISO date string"):
        acceptance_handler._iso_date(1234)

    assert acceptance_handler._tenant_tier(None) == PricingTier.FREE
    assert acceptance_handler._tenant_tier("pro") == PricingTier.PRO

    assert (
        acceptance_handler._integration_event_type("unknown-channel")
        == AuditEventType.INTEGRATION_TEST_SUITE
    )
    assert (
        acceptance_handler._integration_event_type("tenancy")
        == AuditEventType.INTEGRATION_TEST_TENANCY
    )


@pytest.mark.asyncio
async def test_acceptance_handler_quarterly_and_close_skip_with_tier_gated_integrations() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="starter")
    job = _job(
        {
            "capture_quarterly_report": "yes",
            "capture_close_package": "true",
        }
    )
    jira = MagicMock()
    jira.health_check = AsyncMock()
    teams = MagicMock()
    teams.health_check = AsyncMock()
    dispatchers = [SimpleNamespace(provider="pagerduty")]

    with _patched_acceptance_environment(
        feature_flags={
            FeatureFlag.COMPLIANCE_EXPORTS: False,
            FeatureFlag.CLOSE_WORKFLOW: False,
            FeatureFlag.INCIDENT_INTEGRATIONS: False,
        },
        jira_service=jira,
        teams_service=teams,
        workflow_dispatchers=dispatchers,
    ) as patched:
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["close_package_capture_requested"] is True
    assert result["close_package_captured"] is True
    jira.health_check.assert_not_awaited()
    teams.health_check.assert_not_awaited()

    quarterly_events = _audit_event_calls(
        patched["audit"], AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED
    )
    assert quarterly_events
    assert quarterly_events[0].kwargs["details"]["skipped"] is True
    assert quarterly_events[0].kwargs["details"]["reason"] == "feature_not_enabled"

    close_events = _audit_event_calls(
        patched["audit"], AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED
    )
    assert close_events
    assert close_events[0].kwargs["details"]["payload"]["reason"] == "feature_not_enabled"


@pytest.mark.asyncio
async def test_acceptance_handler_quarterly_success_and_close_error_with_bad_max_restatements() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="pro")
    job = _job(
        {
            "capture_quarterly_report": True,
            "capture_close_package": True,
            "close_max_restatement_entries": "bad",
            "close_provider": " AWS ",
        }
    )

    quarterly_payload = _model_payload({"year": 2026, "quarter": 1})
    quarterly_payload.year = 2026
    quarterly_payload.quarter = 1

    with _patched_acceptance_environment(
        feature_flags={
            FeatureFlag.COMPLIANCE_EXPORTS: True,
            FeatureFlag.CLOSE_WORKFLOW: True,
            FeatureFlag.INCIDENT_INTEGRATIONS: False,
        },
        quarterly_payload=quarterly_payload,
        close_package_side_effect=RuntimeError("close package failed"),
    ) as patched:
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["close_package_capture_requested"] is True
    assert result["close_package_captured"] is False
    assert "close package failed" in str(result["close_package_error"])

    quarterly_events = _audit_event_calls(
        patched["audit"], AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED
    )
    assert quarterly_events
    assert quarterly_events[0].kwargs["resource_id"] == "2026-Q1"
    assert quarterly_events[0].kwargs["success"] is True

    close_events = _audit_event_calls(
        patched["audit"], AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED
    )
    assert close_events
    assert close_events[0].kwargs["success"] is False
    assert "close package failed" in str(close_events[0].kwargs["error_message"])
    patched["close_package"].assert_awaited_once()
    assert patched["close_package"].await_args.kwargs["max_restatement_entries"] == 25


@pytest.mark.asyncio
async def test_acceptance_handler_clamps_negative_close_restatements_and_records_integration_health() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="pro")
    job = _job({"capture_close_package": True, "close_max_restatement_entries": -5})

    slack = MagicMock()
    slack.health_check = AsyncMock(side_effect=RuntimeError("slack timeout"))
    jira = MagicMock()
    jira.health_check = AsyncMock(return_value=(False, 503, "jira unavailable"))
    teams = MagicMock()
    teams.health_check = AsyncMock(return_value=(True, 200, None))
    dispatchers = [SimpleNamespace(provider="pagerduty"), SimpleNamespace(provider="jira")]

    with _patched_acceptance_environment(
        feature_flags={
            FeatureFlag.COMPLIANCE_EXPORTS: True,
            FeatureFlag.CLOSE_WORKFLOW: True,
            FeatureFlag.INCIDENT_INTEGRATIONS: True,
        },
        slack_service=slack,
        jira_service=jira,
        teams_service=teams,
        workflow_dispatchers=dispatchers,
        close_package_payload={
            "close_status": "ready",
            "csv": "should be removed",
            "integrity_hash": "abc123",
        },
    ) as patched:
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["close_package_capture_requested"] is True
    assert result["close_package_captured"] is True
    assert result["integrations"]["overall_status"] == "partial_failure"
    assert result["integrations"]["failed"] >= 1

    patched["logger"].warning.assert_any_call(
        "slack_passive_health_check_exception",
        error="slack timeout",
        tenant_id=str(job.tenant_id),
    )
    assert patched["close_package"].await_args.kwargs["max_restatement_entries"] == 0

    close_events = _audit_event_calls(
        patched["audit"], AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED
    )
    assert close_events
    payload = close_events[0].kwargs["details"]["payload"]
    assert "csv" not in payload


@pytest.mark.asyncio
async def test_acceptance_handler_records_leadership_and_quarterly_capture_exceptions() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="pro")
    job = _job({"capture_quarterly_report": True})

    with _patched_acceptance_environment(
        feature_flags={
            FeatureFlag.COMPLIANCE_EXPORTS: True,
            FeatureFlag.CLOSE_WORKFLOW: False,
            FeatureFlag.INCIDENT_INTEGRATIONS: False,
        },
        quarterly_side_effect=RuntimeError("quarterly capture blew up"),
    ) as patched:
        patched["leadership_compute"].side_effect = RuntimeError("leadership capture blew up")
        result = await handler.execute(job, db)

    assert result["status"] == "completed"

    patched["logger"].warning.assert_any_call(
        "leadership_kpi_capture_failed",
        tenant_id=str(job.tenant_id),
        error="leadership capture blew up",
    )
    patched["logger"].warning.assert_any_call(
        "commercial_quarterly_report_capture_failed",
        tenant_id=str(job.tenant_id),
        error="quarterly capture blew up",
    )

    leadership_events = _audit_event_calls(
        patched["audit"], AuditEventType.LEADERSHIP_KPIS_CAPTURED
    )
    assert leadership_events
    assert leadership_events[0].kwargs["success"] is False
    assert leadership_events[0].kwargs["details"]["error"] == "leadership capture blew up"

    quarterly_events = _audit_event_calls(
        patched["audit"], AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED
    )
    assert quarterly_events
    assert quarterly_events[0].kwargs["success"] is False
    assert quarterly_events[0].kwargs["resource_id"] == "previous_quarter"
    assert quarterly_events[0].kwargs["details"]["error"] == "quarterly capture blew up"


@pytest.mark.asyncio
async def test_acceptance_handler_records_kpi_capture_exception() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="starter")
    job = _job()

    with _patched_acceptance_environment(
        feature_flags={
            FeatureFlag.COMPLIANCE_EXPORTS: False,
            FeatureFlag.CLOSE_WORKFLOW: False,
            FeatureFlag.INCIDENT_INTEGRATIONS: False,
        },
        kpi_side_effect=RuntimeError("acceptance kpi blew up"),
    ) as patched:
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    patched["logger"].warning.assert_any_call(
        "acceptance_kpi_capture_failed",
        tenant_id=str(job.tenant_id),
        error="acceptance kpi blew up",
    )

    kpi_events = _audit_event_calls(patched["audit"], AuditEventType.ACCEPTANCE_KPIS_CAPTURED)
    assert kpi_events
    assert kpi_events[0].kwargs["success"] is False
    assert kpi_events[0].kwargs["details"]["error"] == "acceptance kpi blew up"


@pytest.mark.asyncio
async def test_acceptance_handler_staging_tenancy_passive_check_fails_when_evidence_missing() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="pro")
    db.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(plan="pro"),
            None,
        ]
    )
    job = _job()

    with (
        _patched_acceptance_environment(
            feature_flags={
                FeatureFlag.COMPLIANCE_EXPORTS: False,
                FeatureFlag.CLOSE_WORKFLOW: False,
                FeatureFlag.INCIDENT_INTEGRATIONS: False,
            },
        ) as patched,
        patch.object(
            acceptance_handler,
            "get_settings",
            return_value=SimpleNamespace(
                ENVIRONMENT="staging",
                TENANT_ISOLATION_EVIDENCE_MAX_AGE_HOURS=24,
            ),
        ),
    ):
        result = await handler.execute(job, db)

    tenancy_results = [
        item
        for item in result["integrations"]["results"]
        if item.get("channel") == "tenancy"
    ]
    assert tenancy_results
    assert tenancy_results[0]["success"] is False

    tenancy_events = _audit_event_calls(
        patched["audit"], AuditEventType.INTEGRATION_TEST_TENANCY
    )
    assert tenancy_events
    assert tenancy_events[0].kwargs["success"] is False
    assert tenancy_events[0].kwargs["details"]["reason"] == "evidence_missing"


@pytest.mark.asyncio
async def test_acceptance_handler_staging_tenancy_passive_check_succeeds_with_fresh_evidence() -> None:
    handler = acceptance_handler.AcceptanceSuiteCaptureHandler()
    db = _db(plan="pro")
    evidence_event = SimpleNamespace(
        event_timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        success=True,
        correlation_id="tenancy-check-1",
    )
    db.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(plan="pro"),
            evidence_event,
        ]
    )
    job = _job()

    with (
        _patched_acceptance_environment(
            feature_flags={
                FeatureFlag.COMPLIANCE_EXPORTS: False,
                FeatureFlag.CLOSE_WORKFLOW: False,
                FeatureFlag.INCIDENT_INTEGRATIONS: False,
            },
        ) as patched,
        patch.object(
            acceptance_handler,
            "get_settings",
            return_value=SimpleNamespace(
                ENVIRONMENT="staging",
                TENANT_ISOLATION_EVIDENCE_MAX_AGE_HOURS=24,
            ),
        ),
    ):
        result = await handler.execute(job, db)

    tenancy_results = [
        item
        for item in result["integrations"]["results"]
        if item.get("channel") == "tenancy"
    ]
    assert tenancy_results
    assert tenancy_results[0]["success"] is True

    tenancy_events = _audit_event_calls(
        patched["audit"], AuditEventType.INTEGRATION_TEST_TENANCY
    )
    assert tenancy_events
    assert tenancy_events[0].kwargs["success"] is True
    assert tenancy_events[0].kwargs["details"]["evidence_correlation_id"] == "tenancy-check-1"
