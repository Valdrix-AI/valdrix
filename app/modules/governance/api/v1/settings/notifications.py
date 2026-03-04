"""
Notification Settings API

Manages Slack/Jira/Teams and alert notification preferences for tenants.
"""
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app.shared.core.auth import (
    CurrentUser,
    get_current_user_with_db_context,
    requires_role_with_db_context,
)
from app.shared.core.logging import audit_log
from app.shared.core.pricing import FeatureFlag, is_feature_enabled, normalize_tier
from app.shared.db.session import get_db
from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.domain.security.audit_log import (
    AuditEventType,
    AuditLog,
    AuditLogger,
)
from app.modules.governance.api.v1.settings.notification_settings_ops import (
    apply_notification_settings_update as _apply_notification_settings_update_impl,
    build_notification_settings_audit_payload as _build_notification_settings_audit_payload_impl,
    build_notification_settings_create_kwargs as _build_notification_settings_create_kwargs_impl,
    enforce_incident_integrations_access as _enforce_incident_integrations_access_impl,
    validate_notification_settings_requirements as _validate_notification_settings_requirements_impl,
)
from app.modules.governance.api.v1.settings.notifications_models import (
    IntegrationAcceptanceCaptureRequest,
    IntegrationAcceptanceCaptureResponse,
    IntegrationAcceptanceEvidenceItem,
    IntegrationAcceptanceEvidenceListResponse,
    IntegrationAcceptanceResult,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    PolicyNotificationDiagnosticsResponse,
)
from app.modules.governance.api.v1.settings.notification_diagnostics_ops import (
    to_jira_policy_diagnostics as _to_jira_policy_diagnostics_impl,
    to_notification_response as _to_notification_response_impl,
    to_slack_policy_diagnostics as _to_slack_policy_diagnostics_impl,
)
logger = structlog.get_logger()
router = APIRouter(tags=["Notifications"])
NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (SQLAlchemyError, RuntimeError, OSError, TimeoutError, ValueError, TypeError, AttributeError, KeyError)

def _raise_http_exception(status_code: int, detail: str) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


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


def _normalize_acceptance_details(
    details: Mapping[str, object] | None,
) -> dict[str, str | int | float | bool | list[str]]:
    normalized: dict[str, str | int | float | bool | list[str]] = {}
    for key, value in (details or {}).items():
        if isinstance(value, (str, int, float, bool)):
            normalized[str(key)] = value
        elif isinstance(value, list):
            normalized[str(key)] = [str(item) for item in value]
        elif value is not None:
            normalized[str(key)] = str(value)
    return normalized


def _coerce_status_code(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.isdigit():
            return int(candidate)
    return None


async def _record_acceptance_evidence(
    *,
    db: AsyncSession,
    user: CurrentUser,
    run_id: str,
    channel: str,
    success: bool,
    status_code: int,
    message: str,
    details: Mapping[str, object] | None = None,
    request_path: str,
) -> None:
    if user.tenant_id is None:
        return
    audit = AuditLogger(db=db, tenant_id=user.tenant_id, correlation_id=run_id)
    await audit.log(
        event_type=_integration_event_type(channel),
        actor_id=None,
        actor_email=user.email,
        resource_type="notification_integration",
        resource_id=channel,
        details={
            "channel": channel,
            "status_code": status_code,
            "result_message": message,
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **_normalize_acceptance_details(details),
        },
        success=success,
        error_message=None if success else message,
        request_method="POST",
        request_path=request_path,
    )


async def _run_slack_connectivity_test(
    *,
    current_user: CurrentUser,
    db: AsyncSession,
) -> IntegrationAcceptanceResult:
    from app.modules.notifications.domain import get_tenant_slack_service

    if current_user.tenant_id is None:
        return IntegrationAcceptanceResult(
            channel="slack",
            event_type=AuditEventType.INTEGRATION_TEST_SLACK.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Tenant context required. Please complete onboarding.",
        )

    slack = await get_tenant_slack_service(db, current_user.tenant_id)
    if slack is None:
        return IntegrationAcceptanceResult(
            channel="slack",
            event_type=AuditEventType.INTEGRATION_TEST_SLACK.value,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=(
                "Slack is not configured for this tenant. "
                "Ensure Slack is enabled and channel settings are set."
            ),
        )

    try:
        ok = await slack.send_alert(
            title="Valdrics Slack Connectivity Test",
            message=f"This is a test alert from Valdrics.\n\nUser: {current_user.email}",
            severity="info",
        )
    except NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS as exc:
        logger.error("slack_test_failed", error=str(exc))
        return IntegrationAcceptanceResult(
            channel="slack",
            event_type=AuditEventType.INTEGRATION_TEST_SLACK.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Slack test failed: {str(exc)}",
        )

    if not ok:
        return IntegrationAcceptanceResult(
            channel="slack",
            event_type=AuditEventType.INTEGRATION_TEST_SLACK.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to send Slack notification",
        )

    return IntegrationAcceptanceResult(
        channel="slack",
        event_type=AuditEventType.INTEGRATION_TEST_SLACK.value,
        success=True,
        status_code=status.HTTP_200_OK,
        message="Test notification sent to Slack",
    )


async def _run_jira_connectivity_test(
    *,
    current_user: CurrentUser,
    db: AsyncSession,
) -> IntegrationAcceptanceResult:
    from app.modules.notifications.domain import get_tenant_jira_service

    if current_user.tenant_id is None:
        return IntegrationAcceptanceResult(
            channel="jira",
            event_type=AuditEventType.INTEGRATION_TEST_JIRA.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Tenant context required. Please complete onboarding.",
        )

    jira = await get_tenant_jira_service(db, current_user.tenant_id)
    if jira is None:
        return IntegrationAcceptanceResult(
            channel="jira",
            event_type=AuditEventType.INTEGRATION_TEST_JIRA.value,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=(
                "Jira is not configured for this tenant. "
                "Set Jira fields in notification settings and keep Jira enabled."
            ),
        )

    try:
        success = await jira.create_issue(
            summary="Valdrics Jira Connectivity Test",
            description=(
                "h2. Connectivity test\n"
                "This issue verifies Valdrics can create Jira incidents for policy events."
            ),
            labels=["valdrics", "connectivity-test"],
        )
    except NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS as exc:
        logger.error("jira_test_failed", error=str(exc))
        return IntegrationAcceptanceResult(
            channel="jira",
            event_type=AuditEventType.INTEGRATION_TEST_JIRA.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Jira test failed: {str(exc)}",
        )

    if not success:
        return IntegrationAcceptanceResult(
            channel="jira",
            event_type=AuditEventType.INTEGRATION_TEST_JIRA.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create Jira test issue",
        )

    return IntegrationAcceptanceResult(
        channel="jira",
        event_type=AuditEventType.INTEGRATION_TEST_JIRA.value,
        success=True,
        status_code=status.HTTP_200_OK,
        message="Test issue created in Jira",
    )


async def _run_teams_connectivity_test(
    *,
    current_user: CurrentUser,
    db: AsyncSession,
) -> IntegrationAcceptanceResult:
    from app.modules.notifications.domain import get_tenant_teams_service

    if current_user.tenant_id is None:
        return IntegrationAcceptanceResult(
            channel="teams",
            event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Tenant context required. Please complete onboarding.",
        )

    tier = normalize_tier(current_user.tier)
    if not is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS):
        return IntegrationAcceptanceResult(
            channel="teams",
            event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message=(
                f"Feature '{FeatureFlag.INCIDENT_INTEGRATIONS.value}' requires an upgrade. "
                f"Current tier: {tier.value}"
            ),
        )

    teams = await get_tenant_teams_service(db, current_user.tenant_id)
    if teams is None:
        return IntegrationAcceptanceResult(
            channel="teams",
            event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=(
                "Teams is not configured for this tenant. "
                "Set Teams webhook URL in notification settings and keep Teams enabled."
            ),
        )

    try:
        ok = await teams.send_alert(
            title="Valdrics Teams Connectivity Test",
            message=f"This is a test alert from Valdrics.\n\nUser: {current_user.email}",
            severity="info",
        )
    except NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS as exc:
        logger.error("teams_test_failed", error=str(exc))
        return IntegrationAcceptanceResult(
            channel="teams",
            event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Teams test failed: {str(exc)}",
        )

    if not ok:
        return IntegrationAcceptanceResult(
            channel="teams",
            event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to send Teams notification",
        )

    return IntegrationAcceptanceResult(
        channel="teams",
        event_type=AuditEventType.INTEGRATION_TEST_TEAMS.value,
        success=True,
        status_code=status.HTTP_200_OK,
        message="Test notification sent to Teams",
    )


async def _run_workflow_connectivity_test(
    *,
    current_user: CurrentUser,
    db: AsyncSession,
) -> IntegrationAcceptanceResult:
    from app.modules.notifications.domain import get_tenant_workflow_dispatchers
    from app.shared.core.notifications import NotificationDispatcher

    if current_user.tenant_id is None:
        return IntegrationAcceptanceResult(
            channel="workflow",
            event_type=AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Tenant context required. Please complete onboarding.",
        )

    tier = normalize_tier(current_user.tier)
    if not is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS):
        return IntegrationAcceptanceResult(
            channel="workflow",
            event_type=AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
            success=False,
            status_code=status.HTTP_403_FORBIDDEN,
            message=(
                f"Feature '{FeatureFlag.INCIDENT_INTEGRATIONS.value}' requires an upgrade. "
                f"Current tier: {tier.value}"
            ),
        )

    dispatchers = await get_tenant_workflow_dispatchers(db, current_user.tenant_id)
    if not dispatchers:
        return IntegrationAcceptanceResult(
            channel="workflow",
            event_type=AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=(
                "No workflow integration is configured for this tenant. "
                "Configure GitHub, GitLab, or webhook workflow settings first."
            ),
        )

    payload = {
        "tenant_id": str(current_user.tenant_id),
        "request_id": None,
        "decision": "warn",
        "summary": "Valdrics workflow connectivity test event",
        "resource_id": "workflow-connectivity-check",
        "action": "test_dispatch",
        "severity": "info",
        "evidence_links": NotificationDispatcher._build_remediation_evidence_links(
            None
        ),
    }

    ok_count = 0
    provider_results: list[str] = []
    for dispatcher in dispatchers:
        provider = str(getattr(dispatcher, "provider", "unknown"))
        try:
            ok = await dispatcher.dispatch("workflow.connectivity_test", payload)
        except NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS as exc:
            logger.warning(
                "workflow_test_dispatch_exception", provider=provider, error=str(exc)
            )
            ok = False
        if ok:
            ok_count += 1
            provider_results.append(f"{provider}:ok")
        else:
            provider_results.append(f"{provider}:failed")

    if ok_count == 0:
        return IntegrationAcceptanceResult(
            channel="workflow",
            event_type=AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Workflow test failed for all configured integrations",
            details={
                "total_targets": len(dispatchers),
                "successful_targets": 0,
                "provider_results": provider_results,
            },
        )

    return IntegrationAcceptanceResult(
        channel="workflow",
        event_type=AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Workflow test dispatched successfully ({ok_count}/{len(dispatchers)} targets).",
        details={
            "total_targets": len(dispatchers),
            "successful_targets": ok_count,
            "provider_results": provider_results,
        },
    )


# ============================================================
# API Endpoints
# ============================================================


@router.get("/notifications", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: CurrentUser = Depends(get_current_user_with_db_context),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    """
    Get notification settings for the current tenant.

    Creates default settings if none exist.
    """
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    # Create default settings if not exists
    if not settings:
        settings = NotificationSettings(
            tenant_id=current_user.tenant_id,
            slack_enabled=True,
            jira_enabled=False,
            jira_issue_type="Task",
            digest_schedule="daily",
            digest_hour=9,
            digest_minute=0,
            alert_on_budget_warning=True,
            alert_on_budget_exceeded=True,
            alert_on_zombie_detected=True,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info(
            "notification_settings_created",
            tenant_id=str(current_user.tenant_id),
        )

    return _to_notification_response_impl(settings)


@router.put("/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    """
    Update notification settings for the current tenant.

    Creates settings if none exist.
    """
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    _enforce_incident_integrations_access_impl(
        data=data,
        current_tier=current_user.tier,
        normalize_tier_fn=normalize_tier,
        is_feature_enabled_fn=is_feature_enabled,
        incident_integrations_feature=FeatureFlag.INCIDENT_INTEGRATIONS,
        raise_http_exception_fn=_raise_http_exception,
    )

    if not settings:
        settings = NotificationSettings(
            **_build_notification_settings_create_kwargs_impl(
                data=data,
                tenant_id=current_user.tenant_id,
            )
        )
        db.add(settings)
    else:
        _apply_notification_settings_update_impl(
            settings=settings,
            updates=data.model_dump(),
        )

    _validate_notification_settings_requirements_impl(
        settings=settings,
        raise_http_exception_fn=_raise_http_exception,
    )

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "notification_settings_updated",
        tenant_id=str(current_user.tenant_id),
        digest_schedule=settings.digest_schedule,
    )

    audit_log(
        "settings.notifications_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        _build_notification_settings_audit_payload_impl(settings),
    )

    return _to_notification_response_impl(settings)


@router.get(
    "/notifications/policy-diagnostics",
    response_model=PolicyNotificationDiagnosticsResponse,
)
async def get_policy_notification_diagnostics(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> PolicyNotificationDiagnosticsResponse:
    """
    Diagnose why policy notifications are or are not deliverable for this tenant.
    """
    from app.shared.core.config import get_settings

    notification_result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    notification_settings = notification_result.scalar_one_or_none()

    remediation_result = await db.execute(
        select(RemediationSettings).where(
            RemediationSettings.tenant_id == current_user.tenant_id
        )
    )
    remediation_settings = remediation_result.scalar_one_or_none()

    tier = normalize_tier(current_user.tier)
    feature_allowed_by_tier = is_feature_enabled(
        tier, FeatureFlag.INCIDENT_INTEGRATIONS
    )

    app_settings = get_settings()
    slack = _to_slack_policy_diagnostics_impl(
        remediation_settings,
        notification_settings,
        has_bot_token=bool(app_settings.SLACK_BOT_TOKEN),
        has_default_channel=bool(app_settings.SLACK_CHANNEL_ID),
    )
    jira = _to_jira_policy_diagnostics_impl(
        remediation_settings,
        notification_settings,
        feature_allowed_by_tier=feature_allowed_by_tier,
    )

    return PolicyNotificationDiagnosticsResponse(
        tier=tier.value,
        has_activeops_settings=remediation_settings is not None,
        has_notification_settings=notification_settings is not None,
        policy_enabled=bool(getattr(remediation_settings, "policy_enabled", True)),
        slack=slack,
        jira=jira,
    )


@router.post("/notifications/test-slack")
async def test_slack_notification(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Send a test notification to Slack.

    Uses the configured Slack channel or override.
    """
    run_id = str(uuid4())
    result = await _run_slack_connectivity_test(current_user=current_user, db=db)
    await _record_acceptance_evidence(
        db=db,
        user=current_user,
        run_id=run_id,
        channel="slack",
        success=result.success,
        status_code=result.status_code,
        message=result.message,
        details=result.details,
        request_path="/api/v1/settings/notifications/test-slack",
    )
    await db.commit()
    if not result.success:
        raise HTTPException(status_code=result.status_code, detail=result.message)
    return {"status": "success", "message": result.message}


@router.post("/notifications/test-jira")
async def test_jira_notification(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Send a test Jira issue using tenant-scoped Jira notification settings.
    """
    run_id = str(uuid4())
    result = await _run_jira_connectivity_test(current_user=current_user, db=db)
    await _record_acceptance_evidence(
        db=db,
        user=current_user,
        run_id=run_id,
        channel="jira",
        success=result.success,
        status_code=result.status_code,
        message=result.message,
        details=result.details,
        request_path="/api/v1/settings/notifications/test-jira",
    )
    await db.commit()
    if not result.success:
        raise HTTPException(status_code=result.status_code, detail=result.message)
    return {"status": "success", "message": result.message}


@router.post("/notifications/test-teams")
async def test_teams_notification(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Send a test notification to Microsoft Teams using tenant-scoped settings.
    """
    run_id = str(uuid4())
    result = await _run_teams_connectivity_test(current_user=current_user, db=db)
    await _record_acceptance_evidence(
        db=db,
        user=current_user,
        run_id=run_id,
        channel="teams",
        success=result.success,
        status_code=result.status_code,
        message=result.message,
        details=result.details,
        request_path="/api/v1/settings/notifications/test-teams",
    )
    await db.commit()
    if not result.success:
        raise HTTPException(status_code=result.status_code, detail=result.message)
    return {"status": "success", "message": result.message}


@router.post("/notifications/test-workflow")
async def test_workflow_notification(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Send a test workflow automation event using tenant-scoped workflow settings.
    """
    run_id = str(uuid4())
    result = await _run_workflow_connectivity_test(current_user=current_user, db=db)
    await _record_acceptance_evidence(
        db=db,
        user=current_user,
        run_id=run_id,
        channel="workflow",
        success=result.success,
        status_code=result.status_code,
        message=result.message,
        details=result.details,
        request_path="/api/v1/settings/notifications/test-workflow",
    )
    await db.commit()
    if not result.success:
        raise HTTPException(status_code=result.status_code, detail=result.message)
    return {"status": "success", "message": result.message}


@router.post(
    "/notifications/acceptance-evidence/capture",
    response_model=IntegrationAcceptanceCaptureResponse,
)
async def capture_notification_acceptance_evidence(
    payload: IntegrationAcceptanceCaptureRequest | None = None,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> IntegrationAcceptanceCaptureResponse:
    """
    Execute integration connectivity checks and persist audit-grade acceptance evidence.
    """
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required. Please complete onboarding.",
        )
    payload = payload or IntegrationAcceptanceCaptureRequest()

    run_id = str(uuid4())
    captured_at = datetime.now(timezone.utc)
    checks: list[
        tuple[
            str,
            Callable[..., Awaitable[IntegrationAcceptanceResult]],
        ]
    ] = []
    if payload.include_slack:
        checks.append(("slack", _run_slack_connectivity_test))
    if payload.include_jira:
        checks.append(("jira", _run_jira_connectivity_test))
    if payload.include_teams:
        checks.append(("teams", _run_teams_connectivity_test))
    if payload.include_workflow:
        checks.append(("workflow", _run_workflow_connectivity_test))
    if not checks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one integration check must be enabled.",
        )

    results: list[IntegrationAcceptanceResult] = []
    for channel, runner in checks:
        channel_result = await runner(current_user=current_user, db=db)
        results.append(channel_result)
        await _record_acceptance_evidence(
            db=db,
            user=current_user,
            run_id=run_id,
            channel=channel,
            success=channel_result.success,
            status_code=channel_result.status_code,
            message=channel_result.message,
            details=channel_result.details,
            request_path="/api/v1/settings/notifications/acceptance-evidence/capture",
        )
        if payload.fail_fast and not channel_result.success:
            break

    passed = sum(1 for item in results if item.success)
    failed = len(results) - passed
    overall_status = (
        "success" if failed == 0 else "partial_failure" if passed > 0 else "failed"
    )

    await _record_acceptance_evidence(
        db=db,
        user=current_user,
        run_id=run_id,
        channel="suite",
        success=(failed == 0),
        status_code=status.HTTP_200_OK if failed == 0 else status.HTTP_207_MULTI_STATUS,
        message=f"Acceptance suite completed ({passed} passed, {failed} failed).",
        details={
            "overall_status": overall_status,
            "passed": passed,
            "failed": failed,
            "checked_channels": [item.channel for item in results],
        },
        request_path="/api/v1/settings/notifications/acceptance-evidence/capture",
    )
    await db.commit()

    return IntegrationAcceptanceCaptureResponse(
        run_id=run_id,
        tenant_id=str(current_user.tenant_id),
        captured_at=captured_at.isoformat(),
        overall_status=overall_status,
        passed=passed,
        failed=failed,
        results=results,
    )


@router.get(
    "/notifications/acceptance-evidence",
    response_model=IntegrationAcceptanceEvidenceListResponse,
)
async def list_notification_acceptance_evidence(
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    run_id: str | None = None,
) -> IntegrationAcceptanceEvidenceListResponse:
    """
    List persisted notification/workflow acceptance evidence for this tenant.
    """
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required. Please complete onboarding.",
        )
    safe_limit = max(1, min(int(limit), 200))
    accepted_event_types = [
        AuditEventType.INTEGRATION_TEST_SLACK.value,
        AuditEventType.INTEGRATION_TEST_JIRA.value,
        AuditEventType.INTEGRATION_TEST_TEAMS.value,
        AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
        AuditEventType.INTEGRATION_TEST_SUITE.value,
    ]
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .where(AuditLog.event_type.in_(accepted_event_types))
        .order_by(desc(AuditLog.event_timestamp))
        .limit(safe_limit)
    )
    if run_id:
        stmt = stmt.where(AuditLog.correlation_id == run_id)
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        IntegrationAcceptanceEvidenceItem(
            event_id=str(row.id),
            run_id=row.correlation_id,
            event_type=row.event_type,
            channel=str(
                (row.details or {}).get("channel", row.resource_id or "unknown")
            ),
            success=bool(row.success),
            status_code=_coerce_status_code((row.details or {}).get("status_code")),
            message=str((row.details or {}).get("result_message", row.error_message))
            if (row.details or {}).get("result_message", row.error_message) is not None
            else None,
            actor_id=str(row.actor_id) if row.actor_id else None,
            actor_email=row.actor_email,
            event_timestamp=row.event_timestamp.isoformat(),
            details=_normalize_acceptance_details(row.details),
        )
        for row in rows
    ]
    return IntegrationAcceptanceEvidenceListResponse(total=len(items), items=items)
