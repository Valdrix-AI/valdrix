"""
Acceptance Suite Evidence Capture Job Handler

Runs on a schedule to capture audit-grade evidence that the system is healthy
enough for production sign-off (ingestion reliability, allocation coverage, etc).

Important: this handler must be non-invasive for tenant integrations. It should
avoid creating Jira issues or sending Slack/Teams messages during automated runs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.models.tenant import Tenant, UserPersona, UserRole
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.modules.notifications.domain import (
    get_tenant_jira_service,
    get_tenant_slack_service,
    get_tenant_teams_service,
    get_tenant_workflow_dispatchers,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    is_feature_enabled,
    normalize_tier,
)

logger = structlog.get_logger()


def _require_tenant_id(job: BackgroundJob) -> UUID:
    if job.tenant_id is None:
        raise ValueError("tenant_id required for acceptance_suite_capture")
    return UUID(str(job.tenant_id))


def _iso_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("Expected ISO date string")


def _tenant_tier(plan: str | None) -> PricingTier:
    if not plan:
        return PricingTier.FREE_TRIAL
    return normalize_tier(plan)


class AcceptanceSuiteCaptureHandler(BaseJobHandler):
    """
    Captures acceptance KPI evidence and non-invasive integration health checks.

    Evidence is stored in immutable audit logs:
    - acceptance.kpis_captured
    - integration_test.* (in passive mode)
    """

    timeout_seconds = 300

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = _require_tenant_id(job)
        payload = job.payload or {}

        # Default acceptance KPI window: last 30 days.
        end_date = (
            _iso_date(payload.get("end_date"))
            if payload.get("end_date")
            else date.today()
        )
        start_date = (
            _iso_date(payload.get("start_date"))
            if payload.get("start_date")
            else end_date - timedelta(days=30)
        )

        ingestion_window_hours = int(payload.get("ingestion_window_hours", 24 * 7))
        ingestion_target_success_rate_percent = float(
            payload.get("ingestion_target_success_rate_percent", 95.0)
        )
        recency_target_hours = int(payload.get("recency_target_hours", 48))
        chargeback_target_percent = float(
            payload.get("chargeback_target_percent", 90.0)
        )
        max_unit_anomalies = int(payload.get("max_unit_anomalies", 0))

        run_id = str(uuid4())
        captured_at = datetime.now(timezone.utc).isoformat()

        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        tier = _tenant_tier(getattr(tenant, "plan", None))

        # We need a CurrentUser-like object because KPI computation is tier-aware.
        system_user = CurrentUser(
            id=uuid4(),
            email="system@valdrix.local",
            tenant_id=tenant_id,
            role=UserRole.ADMIN,
            tier=tier,
            persona=UserPersona.PLATFORM,
        )

        audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)

        # 1) Capture acceptance KPI evidence (audit-grade snapshot).
        kpi_success = True
        kpi_error: str | None = None
        acceptance_payload: Any | None = None
        try:
            # NOTE: This is implemented in the Costs API module today.
            # If this grows, extract into a domain service to avoid API-layer imports.
            from app.modules.reporting.api.v1.costs import (
                _compute_acceptance_kpis_payload,
            )

            acceptance_payload = await _compute_acceptance_kpis_payload(
                start_date=start_date,
                end_date=end_date,
                ingestion_window_hours=ingestion_window_hours,
                ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
                recency_target_hours=recency_target_hours,
                chargeback_target_percent=chargeback_target_percent,
                max_unit_anomalies=max_unit_anomalies,
                current_user=system_user,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001 - evidence capture must be resilient
            kpi_success = False
            kpi_error = str(exc)
            logger.warning(
                "acceptance_kpi_capture_failed",
                tenant_id=str(tenant_id),
                error=kpi_error,
            )

        await audit.log(
            event_type=AuditEventType.ACCEPTANCE_KPIS_CAPTURED,
            actor_id=None,
            actor_email=system_user.email,
            resource_type="acceptance_kpis",
            resource_id=f"{start_date.isoformat()}:{end_date.isoformat()}",
            details={
                "run_id": run_id,
                "captured_at": captured_at,
                "thresholds": {
                    "ingestion_window_hours": ingestion_window_hours,
                    "ingestion_target_success_rate_percent": ingestion_target_success_rate_percent,
                    "recency_target_hours": recency_target_hours,
                    "chargeback_target_percent": chargeback_target_percent,
                    "max_unit_anomalies": max_unit_anomalies,
                },
                "tier": tier.value,
                "acceptance_kpis": acceptance_payload.model_dump()
                if acceptance_payload is not None
                and hasattr(acceptance_payload, "model_dump")
                else acceptance_payload,
                "error": kpi_error,
            },
            success=kpi_success,
            error_message=None if kpi_success else (kpi_error or "KPI capture failed"),
            request_method="JOB",
            request_path="/jobs/acceptance-suite-capture",
        )

        # 1b) Capture leadership KPI export evidence (tier-gated, non-invasive).
        # This provides procurement-ready, executive-friendly proof artifacts (spend + carbon + savings proof).
        if is_feature_enabled(tier, FeatureFlag.COMPLIANCE_EXPORTS):
            leadership_success = True
            leadership_error: str | None = None
            leadership_payload: Any | None = None
            try:
                from app.modules.reporting.domain.leadership_kpis import (
                    LeadershipKpiService,
                )

                leadership_payload = await LeadershipKpiService(db).compute(
                    tenant_id=tenant_id,
                    tier=tier,
                    start_date=start_date,
                    end_date=end_date,
                    provider=None,
                    include_preliminary=False,
                    top_services_limit=10,
                )
            except Exception as exc:  # noqa: BLE001 - evidence capture must be resilient
                leadership_success = False
                leadership_error = str(exc)
                logger.warning(
                    "leadership_kpi_capture_failed",
                    tenant_id=str(tenant_id),
                    error=leadership_error,
                )

            await audit.log(
                event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED,
                actor_id=None,
                actor_email=system_user.email,
                resource_type="leadership_kpis",
                resource_id=f"{start_date.isoformat()}:{end_date.isoformat()}",
                details={
                    "run_id": run_id,
                    "captured_at": captured_at,
                    "tier": tier.value,
                    "leadership_kpis": leadership_payload.model_dump()
                    if leadership_payload is not None
                    and hasattr(leadership_payload, "model_dump")
                    else leadership_payload,
                    "error": leadership_error,
                },
                success=leadership_success,
                error_message=None
                if leadership_success
                else (leadership_error or "Leadership KPI capture failed"),
                request_method="JOB",
                request_path="/jobs/acceptance-suite-capture",
            )

        # 1c) Optional quarterly commercial proof report capture (scheduled procurement template).
        quarterly_capture_requested_raw = payload.get("capture_quarterly_report", False)
        quarterly_capture_requested = quarterly_capture_requested_raw is True or str(
            quarterly_capture_requested_raw
        ).strip().lower() in {"1", "true", "yes", "y"}
        if quarterly_capture_requested:
            if not is_feature_enabled(tier, FeatureFlag.COMPLIANCE_EXPORTS):
                await audit.log(
                    event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED,
                    actor_id=None,
                    actor_email=system_user.email,
                    resource_type="commercial_quarterly_report",
                    resource_id="previous_quarter",
                    details={
                        "run_id": run_id,
                        "captured_at": captured_at,
                        "skipped": True,
                        "reason": "feature_not_enabled",
                        "tier": tier.value,
                    },
                    success=True,
                    request_method="JOB",
                    request_path="/jobs/acceptance-suite-capture",
                )
            else:
                quarterly_success = True
                quarterly_error: str | None = None
                quarterly_payload: Any | None = None
                try:
                    from app.modules.reporting.domain.commercial_reports import (
                        CommercialProofReportService,
                    )

                    quarterly_payload = await CommercialProofReportService(
                        db
                    ).quarterly_report(
                        tenant_id=tenant_id,
                        tier=tier,
                        period="previous",
                        as_of=end_date,
                        provider=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    quarterly_success = False
                    quarterly_error = str(exc)
                    logger.warning(
                        "commercial_quarterly_report_capture_failed",
                        tenant_id=str(tenant_id),
                        error=quarterly_error,
                    )

                resource_id = None
                if quarterly_payload is not None and isinstance(
                    getattr(quarterly_payload, "year", None), int
                ):
                    resource_id = f"{getattr(quarterly_payload, 'year', 'unknown')}-Q{getattr(quarterly_payload, 'quarter', 'unknown')}"

                await audit.log(
                    event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED,
                    actor_id=None,
                    actor_email=system_user.email,
                    resource_type="commercial_quarterly_report",
                    resource_id=resource_id or "previous_quarter",
                    details={
                        "run_id": run_id,
                        "captured_at": captured_at,
                        "tier": tier.value,
                        "quarterly_report": quarterly_payload.model_dump()
                        if quarterly_payload is not None
                        and hasattr(quarterly_payload, "model_dump")
                        else quarterly_payload,
                        "error": quarterly_error,
                    },
                    success=quarterly_success,
                    error_message=None
                    if quarterly_success
                    else (
                        quarterly_error
                        or "Quarterly commercial proof report capture failed"
                    ),
                    request_method="JOB",
                    request_path="/jobs/acceptance-suite-capture",
                )

        # 2) Optional month-end close package evidence capture (non-invasive).
        close_capture_requested_raw = payload.get("capture_close_package", False)
        close_capture_requested = close_capture_requested_raw is True or str(
            close_capture_requested_raw
        ).strip().lower() in {"1", "true", "yes", "y"}
        close_capture_success = False
        close_capture_error: str | None = None
        close_capture_payload: dict[str, Any] | None = None

        if close_capture_requested:
            if not is_feature_enabled(tier, FeatureFlag.CLOSE_WORKFLOW):
                close_capture_payload = {
                    "skipped": True,
                    "reason": "feature_not_enabled",
                    "tier": tier.value,
                }
                close_capture_success = True
            else:
                # Previous full calendar month window (deterministic for procurement evidence).
                window_anchor = end_date
                close_end = window_anchor.replace(day=1) - timedelta(days=1)
                close_start = close_end.replace(day=1)
                close_provider = payload.get("close_provider")
                max_restatements_raw = payload.get("close_max_restatement_entries", 25)
                try:
                    max_restatements = int(max_restatements_raw)
                except Exception:
                    max_restatements = 25
                if max_restatements < 0:
                    max_restatements = 0

                try:
                    from app.modules.reporting.domain.reconciliation import (
                        CostReconciliationService,
                    )

                    service = CostReconciliationService(db)
                    package = await service.generate_close_package(
                        tenant_id=tenant_id,
                        start_date=close_start,
                        end_date=close_end,
                        enforce_finalized=False,  # evidence capture should report readiness, not fail hard
                        provider=str(close_provider).strip().lower()
                        if isinstance(close_provider, str) and close_provider
                        else None,
                        max_restatement_entries=max_restatements,
                    )
                    # Never store the CSV blob in audit logs.
                    package.pop("csv", None)
                    close_capture_payload = package
                    close_capture_success = True
                except Exception as exc:  # noqa: BLE001
                    close_capture_error = str(exc)
                    logger.warning(
                        "acceptance_close_package_capture_failed",
                        tenant_id=str(tenant_id),
                        error=close_capture_error,
                    )

            await audit.log(
                event_type=AuditEventType.ACCEPTANCE_CLOSE_PACKAGE_CAPTURED,
                actor_id=None,
                actor_email=system_user.email,
                resource_type="close_package",
                resource_id="previous_month",
                details={
                    "run_id": run_id,
                    "captured_at": captured_at,
                    "requested": True,
                    "payload": close_capture_payload,
                    "error": close_capture_error,
                },
                success=close_capture_success,
                error_message=None
                if close_capture_success
                else (close_capture_error or "Close package capture failed"),
                request_method="JOB",
                request_path="/jobs/acceptance-suite-capture",
            )

        # 3) Passive integration health checks (no side effects).
        integration_results: list[dict[str, Any]] = []

        async def record_integration(
            *,
            channel: str,
            success: bool,
            status_code: int,
            message: str,
            details: dict[str, Any] | None = None,
        ) -> None:
            integration_results.append(
                {
                    "channel": channel,
                    "success": success,
                    "status_code": status_code,
                    "message": message,
                    "details": details or {},
                }
            )
            await audit.log(
                event_type=_integration_event_type(channel),
                actor_id=None,
                actor_email=system_user.email,
                resource_type="notification_integration",
                resource_id=channel,
                details={
                    "channel": channel,
                    "mode": "passive",
                    "status_code": status_code,
                    "result_message": message,
                    "run_id": run_id,
                    "captured_at": captured_at,
                    **(details or {}),
                },
                success=success,
                error_message=None if success else message,
                request_method="JOB",
                request_path="/jobs/acceptance-suite-capture",
            )

        # Slack (passive: auth_test)
        slack = await get_tenant_slack_service(db, tenant_id)
        if slack is None:
            await record_integration(
                channel="slack",
                success=True,
                status_code=204,
                message="Slack not configured for this tenant (skipped).",
                details={"skipped": True, "reason": "not_configured"},
            )
        else:
            try:
                ok = await slack.health_check()
            except Exception as exc:  # noqa: BLE001
                ok = False
                logger.warning(
                    "slack_passive_health_check_exception",
                    error=str(exc),
                    tenant_id=str(tenant_id),
                )
            await record_integration(
                channel="slack",
                success=bool(ok),
                status_code=200 if ok else 502,
                message="Slack passive health check OK."
                if ok
                else "Slack passive health check failed.",
            )

        # Jira (passive: /myself)
        # Jira/workflow are part of "incident integrations" and are tier-gated.
        incident_integrations_allowed = is_feature_enabled(
            tier, FeatureFlag.INCIDENT_INTEGRATIONS
        )
        jira = await get_tenant_jira_service(db, tenant_id)
        if jira is None:
            await record_integration(
                channel="jira",
                success=True,
                status_code=204,
                message="Jira not configured for this tenant (skipped).",
                details={"skipped": True, "reason": "not_configured"},
            )
        elif not incident_integrations_allowed:
            await record_integration(
                channel="jira",
                success=True,
                status_code=204,
                message="Jira configured but incident integrations are not enabled for this tier (skipped).",
                details={
                    "skipped": True,
                    "reason": "tier_not_allowed",
                    "tier": tier.value,
                },
            )
        else:
            ok, status_code, error = await jira.health_check()
            await record_integration(
                channel="jira",
                success=bool(ok),
                status_code=int(status_code or (200 if ok else 502)),
                message="Jira passive health check OK."
                if ok
                else "Jira passive health check failed.",
                details={"error": error} if error else None,
            )

        # Workflow dispatchers (passive: config presence; no dispatch)
        # Teams (passive: URL validation only; no message dispatch during scheduled runs).
        teams = await get_tenant_teams_service(db, tenant_id)
        if teams is None:
            await record_integration(
                channel="teams",
                success=True,
                status_code=204,
                message="Teams not configured for this tenant (skipped).",
                details={"skipped": True, "reason": "not_configured"},
            )
        elif not incident_integrations_allowed:
            await record_integration(
                channel="teams",
                success=True,
                status_code=204,
                message="Teams configured but incident integrations are not enabled for this tier (skipped).",
                details={
                    "skipped": True,
                    "reason": "tier_not_allowed",
                    "tier": tier.value,
                },
            )
        else:
            ok, status_code, error = await teams.health_check()
            await record_integration(
                channel="teams",
                success=bool(ok),
                status_code=int(status_code or (200 if ok else 502)),
                message="Teams passive health check OK."
                if ok
                else "Teams passive health check failed.",
                details={"error": error} if error else None,
            )

        # Workflow dispatchers (passive: config presence; no dispatch)
        dispatchers = await get_tenant_workflow_dispatchers(db, tenant_id)
        providers = [str(getattr(item, "provider", "unknown")) for item in dispatchers]
        if not dispatchers:
            await record_integration(
                channel="workflow",
                success=True,
                status_code=204,
                message="Workflow automation not configured for this tenant (skipped).",
                details={"skipped": True, "reason": "not_configured"},
            )
        elif not incident_integrations_allowed:
            await record_integration(
                channel="workflow",
                success=True,
                status_code=204,
                message="Workflow configured but incident integrations are not enabled for this tier (skipped).",
                details={
                    "skipped": True,
                    "reason": "tier_not_allowed",
                    "tier": tier.value,
                    "providers": providers,
                },
            )
        else:
            await record_integration(
                channel="workflow",
                success=True,
                status_code=200,
                message=f"Workflow dispatchers configured ({len(dispatchers)}). Passive check skipped.",
                details={"providers": providers, "checked": False},
            )

        passed = sum(1 for item in integration_results if item.get("success"))
        failed = len(integration_results) - passed
        overall_status = (
            "success" if failed == 0 else "partial_failure" if passed > 0 else "failed"
        )
        await audit.log(
            event_type=AuditEventType.INTEGRATION_TEST_SUITE,
            actor_id=None,
            actor_email=system_user.email,
            resource_type="notification_integration",
            resource_id="suite",
            details={
                "channel": "suite",
                "mode": "passive",
                "overall_status": overall_status,
                "passed": passed,
                "failed": failed,
                "checked_channels": [
                    item.get("channel") for item in integration_results
                ],
                "run_id": run_id,
                "captured_at": captured_at,
            },
            success=(failed == 0),
            error_message=None if failed == 0 else f"{failed} integrations failed",
            request_method="JOB",
            request_path="/jobs/acceptance-suite-capture",
        )

        # Leave commit responsibility to JobProcessor; it uses a savepoint per job.
        return {
            "status": "completed",
            "tenant_id": str(tenant_id),
            "run_id": run_id,
            "captured_at": captured_at,
            "tier": tier.value,
            "acceptance_kpis_captured": kpi_success,
            "close_package_capture_requested": close_capture_requested,
            "close_package_captured": close_capture_success
            if close_capture_requested
            else False,
            "close_package_error": close_capture_error,
            "integrations": {
                "overall_status": overall_status,
                "passed": passed,
                "failed": failed,
                "results": integration_results,
            },
        }


def _integration_event_type(channel: str) -> AuditEventType:
    normalized = channel.strip().lower()
    if normalized == "slack":
        return AuditEventType.INTEGRATION_TEST_SLACK
    if normalized == "jira":
        return AuditEventType.INTEGRATION_TEST_JIRA
    if normalized == "teams":
        return AuditEventType.INTEGRATION_TEST_TEAMS
    if normalized == "workflow":
        return AuditEventType.INTEGRATION_TEST_WORKFLOW
    return AuditEventType.INTEGRATION_TEST_SUITE
