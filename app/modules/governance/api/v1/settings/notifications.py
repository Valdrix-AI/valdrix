"""
Notification Settings API

Manages Slack/Jira/Teams and alert notification preferences for tenants.
"""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
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

logger = structlog.get_logger()
router = APIRouter(tags=["Notifications"])


# ============================================================
# Pydantic Schemas
# ============================================================


class NotificationSettingsResponse(BaseModel):
    """Response for notification settings."""

    slack_enabled: bool
    slack_channel_override: str | None
    jira_enabled: bool
    jira_base_url: str | None
    jira_email: str | None
    jira_project_key: str | None
    jira_issue_type: str
    has_jira_api_token: bool
    teams_enabled: bool
    teams_webhook_url: str | None
    has_teams_webhook_url: bool
    digest_schedule: str  # "daily", "weekly", "disabled"
    digest_hour: int  # 0-23
    digest_minute: int  # 0-59
    alert_on_budget_warning: bool
    alert_on_budget_exceeded: bool
    alert_on_zombie_detected: bool
    workflow_github_enabled: bool
    workflow_github_owner: str | None
    workflow_github_repo: str | None
    workflow_github_workflow_id: str | None
    workflow_github_ref: str
    workflow_has_github_token: bool
    workflow_gitlab_enabled: bool
    workflow_gitlab_base_url: str
    workflow_gitlab_project_id: str | None
    workflow_gitlab_ref: str
    workflow_has_gitlab_trigger_token: bool
    workflow_webhook_enabled: bool
    workflow_webhook_url: str | None
    workflow_has_webhook_bearer_token: bool

    model_config = ConfigDict(from_attributes=True)


class PolicyChannelDiagnostics(BaseModel):
    """Readiness details for a policy notification channel."""

    enabled_for_policy: bool
    enabled_in_notifications: bool
    ready: bool
    reasons: list[str] = Field(default_factory=list)


class SlackPolicyDiagnostics(PolicyChannelDiagnostics):
    """Slack-specific policy diagnostics."""

    has_bot_token: bool
    has_default_channel: bool
    has_channel_override: bool
    selected_channel: str | None
    channel_source: str  # tenant_override | env_default | none


class JiraPolicyDiagnostics(PolicyChannelDiagnostics):
    """Jira-specific policy diagnostics."""

    feature_allowed_by_tier: bool
    has_base_url: bool
    has_email: bool
    has_project_key: bool
    has_api_token: bool
    issue_type: str


class PolicyNotificationDiagnosticsResponse(BaseModel):
    """Policy-notification delivery diagnostics for the current tenant."""

    tier: str
    has_activeops_settings: bool
    has_notification_settings: bool
    policy_enabled: bool
    slack: SlackPolicyDiagnostics
    jira: JiraPolicyDiagnostics


class NotificationSettingsUpdate(BaseModel):
    """Request to update notification settings."""

    slack_enabled: bool = Field(True, description="Enable/disable Slack notifications")
    slack_channel_override: str | None = Field(
        None,
        max_length=64,
        pattern=r"^(#[\w-]+|[CU][A-Z0-9]+)?$",
        description="Override Slack channel ID (e.g., #general or C0123456789)",
    )
    jira_enabled: bool = Field(False, description="Enable/disable Jira notifications")
    jira_base_url: str | None = Field(
        None,
        max_length=255,
        pattern=r"^https://",
        description="Jira site URL (must be HTTPS), e.g. https://your-org.atlassian.net",
    )
    jira_email: EmailStr | None = Field(
        None, description="Jira account email for API token auth"
    )
    jira_project_key: str | None = Field(
        None,
        max_length=32,
        pattern=r"^[A-Z][A-Z0-9_]{1,31}$",
        description="Jira project key, e.g. FINOPS",
    )
    jira_issue_type: str = Field(
        "Task", max_length=64, description="Issue type used for policy incidents"
    )
    jira_api_token: str | None = Field(
        None,
        min_length=8,
        max_length=1024,
        description="Jira API token. Leave empty to keep current token.",
    )
    clear_jira_api_token: bool = Field(
        False, description="Clear existing Jira API token"
    )
    teams_enabled: bool = Field(
        False, description="Enable/disable Microsoft Teams notifications"
    )
    teams_webhook_url: str | None = Field(
        None,
        max_length=1024,
        pattern=r"^https://",
        description="Microsoft Teams incoming webhook URL (HTTPS). Leave empty to keep current URL.",
    )
    clear_teams_webhook_url: bool = Field(
        False,
        description="Clear existing Teams webhook URL",
    )
    digest_schedule: str = Field(
        "daily", pattern="^(daily|weekly|disabled)$", description="Digest frequency"
    )
    digest_hour: int = Field(9, ge=0, le=23, description="Hour to send digest (UTC)")
    digest_minute: int = Field(0, ge=0, le=59, description="Minute to send digest")
    alert_on_budget_warning: bool = Field(
        True, description="Alert when approaching budget"
    )
    alert_on_budget_exceeded: bool = Field(
        True, description="Alert when budget exceeded"
    )
    alert_on_zombie_detected: bool = Field(
        True, description="Alert on zombie resources"
    )
    workflow_github_enabled: bool = Field(
        False, description="Enable GitHub Actions workflow dispatch"
    )
    workflow_github_owner: str | None = Field(
        None,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="GitHub repository owner/org",
    )
    workflow_github_repo: str | None = Field(
        None,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="GitHub repository name",
    )
    workflow_github_workflow_id: str | None = Field(
        None,
        max_length=200,
        description="GitHub workflow file name or workflow ID",
    )
    workflow_github_ref: str = Field(
        "main", max_length=100, description="GitHub workflow ref/branch"
    )
    workflow_github_token: str | None = Field(
        None,
        min_length=8,
        max_length=1024,
        description="GitHub token for workflow dispatch. Leave empty to keep current token.",
    )
    clear_workflow_github_token: bool = Field(
        False, description="Clear stored GitHub workflow token"
    )
    workflow_gitlab_enabled: bool = Field(
        False, description="Enable GitLab CI trigger dispatch"
    )
    workflow_gitlab_base_url: str = Field(
        "https://gitlab.com",
        max_length=255,
        pattern=r"^https://",
        description="GitLab base URL",
    )
    workflow_gitlab_project_id: str | None = Field(
        None,
        max_length=128,
        description="GitLab project ID/path for trigger API",
    )
    workflow_gitlab_ref: str = Field(
        "main", max_length=100, description="GitLab pipeline ref"
    )
    workflow_gitlab_trigger_token: str | None = Field(
        None,
        min_length=8,
        max_length=1024,
        description="GitLab trigger token. Leave empty to keep current token.",
    )
    clear_workflow_gitlab_trigger_token: bool = Field(
        False, description="Clear stored GitLab trigger token"
    )
    workflow_webhook_enabled: bool = Field(
        False, description="Enable generic CI webhook dispatch"
    )
    workflow_webhook_url: str | None = Field(
        None,
        max_length=500,
        pattern=r"^https://",
        description="Generic CI webhook URL (HTTPS)",
    )
    workflow_webhook_bearer_token: str | None = Field(
        None,
        min_length=8,
        max_length=1024,
        description="Bearer token for generic CI webhook. Leave empty to keep current token.",
    )
    clear_workflow_webhook_bearer_token: bool = Field(
        False, description="Clear stored generic CI webhook bearer token"
    )

    @model_validator(mode="after")
    def validate_jira_token_mutation(self) -> "NotificationSettingsUpdate":
        if self.jira_api_token and self.clear_jira_api_token:
            raise ValueError("Provide jira_api_token or clear_jira_api_token, not both")
        if self.teams_webhook_url and self.clear_teams_webhook_url:
            raise ValueError(
                "Provide teams_webhook_url or clear_teams_webhook_url, not both"
            )
        if self.workflow_github_token and self.clear_workflow_github_token:
            raise ValueError(
                "Provide workflow_github_token or clear_workflow_github_token, not both"
            )
        if (
            self.workflow_gitlab_trigger_token
            and self.clear_workflow_gitlab_trigger_token
        ):
            raise ValueError(
                "Provide workflow_gitlab_trigger_token or clear_workflow_gitlab_trigger_token, not both"
            )
        if (
            self.workflow_webhook_bearer_token
            and self.clear_workflow_webhook_bearer_token
        ):
            raise ValueError(
                "Provide workflow_webhook_bearer_token or clear_workflow_webhook_bearer_token, not both"
            )
        return self


class IntegrationAcceptanceResult(BaseModel):
    """Single integration acceptance check result."""

    channel: str
    event_type: str
    success: bool
    status_code: int
    message: str
    details: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict
    )


class IntegrationAcceptanceCaptureRequest(BaseModel):
    """Request options for acceptance evidence capture."""

    include_slack: bool = True
    include_jira: bool = True
    include_teams: bool = True
    include_workflow: bool = True
    fail_fast: bool = False


class IntegrationAcceptanceCaptureResponse(BaseModel):
    """Response for captured integration acceptance evidence."""

    run_id: str
    tenant_id: str
    captured_at: str
    overall_status: str
    passed: int
    failed: int
    results: list[IntegrationAcceptanceResult]


class IntegrationAcceptanceEvidenceItem(BaseModel):
    """Persisted integration acceptance evidence record."""

    event_id: str
    run_id: str | None
    event_type: str
    channel: str
    success: bool
    status_code: int | None
    message: str | None
    actor_id: str | None
    actor_email: str | None
    event_timestamp: str
    details: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict
    )


class IntegrationAcceptanceEvidenceListResponse(BaseModel):
    """Paginated acceptance evidence list."""

    total: int
    items: list[IntegrationAcceptanceEvidenceItem]


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
            title="Valdrix Slack Connectivity Test",
            message=f"This is a test alert from Valdrix.\n\nUser: {current_user.email}",
            severity="info",
        )
    except Exception as exc:
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
            summary="Valdrix Jira Connectivity Test",
            description=(
                "h2. Connectivity test\n"
                "This issue verifies Valdrix can create Jira incidents for policy events."
            ),
            labels=["valdrix", "connectivity-test"],
        )
    except Exception as exc:
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
            title="Valdrix Teams Connectivity Test",
            message=f"This is a test alert from Valdrix.\n\nUser: {current_user.email}",
            severity="info",
        )
    except Exception as exc:
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
        "summary": "Valdrix workflow connectivity test event",
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
        except Exception as exc:
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


def _to_notification_response(
    settings: NotificationSettings,
) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        slack_enabled=bool(getattr(settings, "slack_enabled", True)),
        slack_channel_override=getattr(settings, "slack_channel_override", None),
        jira_enabled=bool(getattr(settings, "jira_enabled", False)),
        jira_base_url=getattr(settings, "jira_base_url", None),
        jira_email=getattr(settings, "jira_email", None),
        jira_project_key=getattr(settings, "jira_project_key", None),
        jira_issue_type=getattr(settings, "jira_issue_type", "Task") or "Task",
        has_jira_api_token=bool(getattr(settings, "jira_api_token", None)),
        teams_enabled=bool(getattr(settings, "teams_enabled", False)),
        teams_webhook_url=None,
        has_teams_webhook_url=bool(getattr(settings, "teams_webhook_url", None)),
        digest_schedule=getattr(settings, "digest_schedule", "daily"),
        digest_hour=int(getattr(settings, "digest_hour", 9)),
        digest_minute=int(getattr(settings, "digest_minute", 0)),
        alert_on_budget_warning=bool(
            getattr(settings, "alert_on_budget_warning", True)
        ),
        alert_on_budget_exceeded=bool(
            getattr(settings, "alert_on_budget_exceeded", True)
        ),
        alert_on_zombie_detected=bool(
            getattr(settings, "alert_on_zombie_detected", True)
        ),
        workflow_github_enabled=bool(
            getattr(settings, "workflow_github_enabled", False)
        ),
        workflow_github_owner=getattr(settings, "workflow_github_owner", None),
        workflow_github_repo=getattr(settings, "workflow_github_repo", None),
        workflow_github_workflow_id=getattr(
            settings, "workflow_github_workflow_id", None
        ),
        workflow_github_ref=(getattr(settings, "workflow_github_ref", None) or "main"),
        workflow_has_github_token=bool(
            getattr(settings, "workflow_github_token", None)
        ),
        workflow_gitlab_enabled=bool(
            getattr(settings, "workflow_gitlab_enabled", False)
        ),
        workflow_gitlab_base_url=(
            getattr(settings, "workflow_gitlab_base_url", None) or "https://gitlab.com"
        ),
        workflow_gitlab_project_id=getattr(
            settings, "workflow_gitlab_project_id", None
        ),
        workflow_gitlab_ref=(getattr(settings, "workflow_gitlab_ref", None) or "main"),
        workflow_has_gitlab_trigger_token=bool(
            getattr(settings, "workflow_gitlab_trigger_token", None)
        ),
        workflow_webhook_enabled=bool(
            getattr(settings, "workflow_webhook_enabled", False)
        ),
        workflow_webhook_url=getattr(settings, "workflow_webhook_url", None),
        workflow_has_webhook_bearer_token=bool(
            getattr(settings, "workflow_webhook_bearer_token", None)
        ),
    )


def _to_slack_policy_diagnostics(
    remediation_settings: RemediationSettings | None,
    notification_settings: NotificationSettings | None,
    *,
    has_bot_token: bool,
    has_default_channel: bool,
) -> SlackPolicyDiagnostics:
    policy_enabled = bool(getattr(remediation_settings, "policy_enabled", True))
    policy_notify_slack = bool(
        getattr(remediation_settings, "policy_violation_notify_slack", True)
    )
    slack_enabled = bool(getattr(notification_settings, "slack_enabled", True))
    channel_override = getattr(notification_settings, "slack_channel_override", None)
    has_channel_override = bool(channel_override)
    selected_channel = channel_override if has_channel_override else None
    if not selected_channel and has_default_channel:
        selected_channel = "configured-via-env-default"

    channel_source = (
        "tenant_override"
        if has_channel_override
        else "env_default"
        if has_default_channel
        else "none"
    )

    reasons: list[str] = []
    if not policy_enabled:
        reasons.append("policy_disabled")
    if not policy_notify_slack:
        reasons.append("policy_slack_notifications_disabled")
    if not slack_enabled:
        reasons.append("tenant_slack_disabled")
    if not has_bot_token:
        reasons.append("missing_slack_bot_token")
    if not has_channel_override and not has_default_channel:
        reasons.append("missing_slack_channel_target")

    return SlackPolicyDiagnostics(
        enabled_for_policy=policy_notify_slack,
        enabled_in_notifications=slack_enabled,
        ready=len(reasons) == 0,
        reasons=reasons,
        has_bot_token=has_bot_token,
        has_default_channel=has_default_channel,
        has_channel_override=has_channel_override,
        selected_channel=selected_channel,
        channel_source=channel_source,
    )


def _to_jira_policy_diagnostics(
    remediation_settings: RemediationSettings | None,
    notification_settings: NotificationSettings | None,
    *,
    feature_allowed_by_tier: bool,
) -> JiraPolicyDiagnostics:
    policy_enabled = bool(getattr(remediation_settings, "policy_enabled", True))
    policy_notify_jira = bool(
        getattr(remediation_settings, "policy_violation_notify_jira", False)
    )
    jira_enabled = bool(getattr(notification_settings, "jira_enabled", False))
    has_base_url = bool(getattr(notification_settings, "jira_base_url", None))
    has_email = bool(getattr(notification_settings, "jira_email", None))
    has_project_key = bool(getattr(notification_settings, "jira_project_key", None))
    has_api_token = bool(getattr(notification_settings, "jira_api_token", None))
    issue_type = (
        getattr(notification_settings, "jira_issue_type", None) or "Task"
    ).strip() or "Task"

    reasons: list[str] = []
    if not policy_enabled:
        reasons.append("policy_disabled")
    if not policy_notify_jira:
        reasons.append("policy_jira_notifications_disabled")
    if not feature_allowed_by_tier:
        reasons.append("tier_missing_incident_integrations_feature")
    if not jira_enabled:
        reasons.append("tenant_jira_disabled")
    if not has_base_url:
        reasons.append("missing_jira_base_url")
    if not has_email:
        reasons.append("missing_jira_email")
    if not has_project_key:
        reasons.append("missing_jira_project_key")
    if not has_api_token:
        reasons.append("missing_jira_api_token")

    return JiraPolicyDiagnostics(
        enabled_for_policy=policy_notify_jira,
        enabled_in_notifications=jira_enabled,
        ready=len(reasons) == 0,
        reasons=reasons,
        feature_allowed_by_tier=feature_allowed_by_tier,
        has_base_url=has_base_url,
        has_email=has_email,
        has_project_key=has_project_key,
        has_api_token=has_api_token,
        issue_type=issue_type,
    )


# ============================================================
# API Endpoints
# ============================================================


@router.get("/notifications", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: CurrentUser = Depends(get_current_user),
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

    return _to_notification_response(settings)


@router.put("/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    if data.jira_enabled:
        tier = normalize_tier(current_user.tier)
        if not is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Feature '{FeatureFlag.INCIDENT_INTEGRATIONS.value}' requires an upgrade. "
                    f"Current tier: {tier.value}"
                ),
            )
    if data.teams_enabled:
        tier = normalize_tier(current_user.tier)
        if not is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Feature '{FeatureFlag.INCIDENT_INTEGRATIONS.value}' requires an upgrade. "
                    f"Current tier: {tier.value}"
                ),
            )
    if (
        data.workflow_github_enabled
        or data.workflow_gitlab_enabled
        or data.workflow_webhook_enabled
    ):
        tier = normalize_tier(current_user.tier)
        if not is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Feature '{FeatureFlag.INCIDENT_INTEGRATIONS.value}' requires an upgrade. "
                    f"Current tier: {tier.value}"
                ),
            )

    if not settings:
        # Create new settings
        settings = NotificationSettings(
            tenant_id=current_user.tenant_id,
            slack_enabled=data.slack_enabled,
            slack_channel_override=data.slack_channel_override,
            jira_enabled=data.jira_enabled,
            jira_base_url=data.jira_base_url,
            jira_email=str(data.jira_email) if data.jira_email else None,
            jira_project_key=data.jira_project_key,
            jira_issue_type=data.jira_issue_type,
            jira_api_token=data.jira_api_token,
            teams_enabled=data.teams_enabled,
            teams_webhook_url=data.teams_webhook_url,
            digest_schedule=data.digest_schedule,
            digest_hour=data.digest_hour,
            digest_minute=data.digest_minute,
            alert_on_budget_warning=data.alert_on_budget_warning,
            alert_on_budget_exceeded=data.alert_on_budget_exceeded,
            alert_on_zombie_detected=data.alert_on_zombie_detected,
            workflow_github_enabled=data.workflow_github_enabled,
            workflow_github_owner=data.workflow_github_owner,
            workflow_github_repo=data.workflow_github_repo,
            workflow_github_workflow_id=data.workflow_github_workflow_id,
            workflow_github_ref=data.workflow_github_ref,
            workflow_github_token=data.workflow_github_token,
            workflow_gitlab_enabled=data.workflow_gitlab_enabled,
            workflow_gitlab_base_url=data.workflow_gitlab_base_url,
            workflow_gitlab_project_id=data.workflow_gitlab_project_id,
            workflow_gitlab_ref=data.workflow_gitlab_ref,
            workflow_gitlab_trigger_token=data.workflow_gitlab_trigger_token,
            workflow_webhook_enabled=data.workflow_webhook_enabled,
            workflow_webhook_url=data.workflow_webhook_url,
            workflow_webhook_bearer_token=data.workflow_webhook_bearer_token,
        )
        db.add(settings)
    else:
        updates = data.model_dump()
        settings.slack_enabled = updates["slack_enabled"]
        settings.slack_channel_override = updates["slack_channel_override"]
        settings.jira_enabled = updates["jira_enabled"]
        settings.jira_base_url = updates["jira_base_url"]
        settings.jira_email = (
            str(updates["jira_email"]) if updates["jira_email"] else None
        )
        settings.jira_project_key = updates["jira_project_key"]
        settings.jira_issue_type = updates["jira_issue_type"]
        if updates["jira_api_token"]:
            settings.jira_api_token = updates["jira_api_token"]
        elif updates["clear_jira_api_token"]:
            settings.jira_api_token = None
        elif not hasattr(settings, "jira_api_token"):
            settings.jira_api_token = None
        settings.teams_enabled = updates["teams_enabled"]
        if updates["teams_webhook_url"]:
            settings.teams_webhook_url = updates["teams_webhook_url"]
        elif updates["clear_teams_webhook_url"]:
            settings.teams_webhook_url = None
        elif not hasattr(settings, "teams_webhook_url"):
            settings.teams_webhook_url = None
        settings.digest_schedule = updates["digest_schedule"]
        settings.digest_hour = updates["digest_hour"]
        settings.digest_minute = updates["digest_minute"]
        settings.alert_on_budget_warning = updates["alert_on_budget_warning"]
        settings.alert_on_budget_exceeded = updates["alert_on_budget_exceeded"]
        settings.alert_on_zombie_detected = updates["alert_on_zombie_detected"]
        settings.workflow_github_enabled = updates["workflow_github_enabled"]
        settings.workflow_github_owner = updates["workflow_github_owner"]
        settings.workflow_github_repo = updates["workflow_github_repo"]
        settings.workflow_github_workflow_id = updates["workflow_github_workflow_id"]
        settings.workflow_github_ref = updates["workflow_github_ref"]
        if updates["workflow_github_token"]:
            settings.workflow_github_token = updates["workflow_github_token"]
        elif updates["clear_workflow_github_token"]:
            settings.workflow_github_token = None

        settings.workflow_gitlab_enabled = updates["workflow_gitlab_enabled"]
        settings.workflow_gitlab_base_url = updates["workflow_gitlab_base_url"]
        settings.workflow_gitlab_project_id = updates["workflow_gitlab_project_id"]
        settings.workflow_gitlab_ref = updates["workflow_gitlab_ref"]
        if updates["workflow_gitlab_trigger_token"]:
            settings.workflow_gitlab_trigger_token = updates[
                "workflow_gitlab_trigger_token"
            ]
        elif updates["clear_workflow_gitlab_trigger_token"]:
            settings.workflow_gitlab_trigger_token = None

        settings.workflow_webhook_enabled = updates["workflow_webhook_enabled"]
        settings.workflow_webhook_url = updates["workflow_webhook_url"]
        if updates["workflow_webhook_bearer_token"]:
            settings.workflow_webhook_bearer_token = updates[
                "workflow_webhook_bearer_token"
            ]
        elif updates["clear_workflow_webhook_bearer_token"]:
            settings.workflow_webhook_bearer_token = None

    if settings.jira_enabled:
        jira_requirements = [
            ("jira_base_url", settings.jira_base_url),
            ("jira_email", settings.jira_email),
            ("jira_project_key", settings.jira_project_key),
            ("jira_api_token", settings.jira_api_token),
        ]
        missing = [name for name, value in jira_requirements if not value]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Jira is enabled but missing required fields: {', '.join(missing)}",
            )
    if settings.teams_enabled and not settings.teams_webhook_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Teams is enabled but missing required field: teams_webhook_url",
        )
    if settings.workflow_github_enabled:
        github_requirements = [
            ("workflow_github_owner", settings.workflow_github_owner),
            ("workflow_github_repo", settings.workflow_github_repo),
            ("workflow_github_workflow_id", settings.workflow_github_workflow_id),
            ("workflow_github_token", settings.workflow_github_token),
        ]
        missing = [name for name, value in github_requirements if not value]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"GitHub workflow dispatch is enabled but missing required fields: {', '.join(missing)}",
            )

    if settings.workflow_gitlab_enabled:
        gitlab_requirements = [
            ("workflow_gitlab_base_url", settings.workflow_gitlab_base_url),
            ("workflow_gitlab_project_id", settings.workflow_gitlab_project_id),
            ("workflow_gitlab_trigger_token", settings.workflow_gitlab_trigger_token),
        ]
        missing = [name for name, value in gitlab_requirements if not value]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"GitLab workflow dispatch is enabled but missing required fields: {', '.join(missing)}",
            )

    if settings.workflow_webhook_enabled and not settings.workflow_webhook_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Webhook workflow dispatch is enabled but missing required field: workflow_webhook_url",
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
        {
            "slack_enabled": settings.slack_enabled,
            "digest": settings.digest_schedule,
            "slack_override": bool(settings.slack_channel_override),
            "jira_enabled": bool(getattr(settings, "jira_enabled", False)),
            "jira_base_url": bool(getattr(settings, "jira_base_url", None)),
            "jira_project_key": getattr(settings, "jira_project_key", None),
            "has_jira_api_token": bool(getattr(settings, "jira_api_token", None)),
            "teams_enabled": bool(getattr(settings, "teams_enabled", False)),
            "has_teams_webhook_url": bool(getattr(settings, "teams_webhook_url", None)),
            "workflow_github_enabled": bool(
                getattr(settings, "workflow_github_enabled", False)
            ),
            "workflow_has_github_token": bool(
                getattr(settings, "workflow_github_token", None)
            ),
            "workflow_gitlab_enabled": bool(
                getattr(settings, "workflow_gitlab_enabled", False)
            ),
            "workflow_has_gitlab_trigger_token": bool(
                getattr(settings, "workflow_gitlab_trigger_token", None)
            ),
            "workflow_webhook_enabled": bool(
                getattr(settings, "workflow_webhook_enabled", False)
            ),
            "workflow_has_webhook_bearer_token": bool(
                getattr(settings, "workflow_webhook_bearer_token", None)
            ),
        },
    )

    return _to_notification_response(settings)


@router.get(
    "/notifications/policy-diagnostics",
    response_model=PolicyNotificationDiagnosticsResponse,
)
async def get_policy_notification_diagnostics(
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    slack = _to_slack_policy_diagnostics(
        remediation_settings,
        notification_settings,
        has_bot_token=bool(app_settings.SLACK_BOT_TOKEN),
        has_default_channel=bool(app_settings.SLACK_CHANNEL_ID),
    )
    jira = _to_jira_policy_diagnostics(
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
    current_user: CurrentUser = Depends(requires_role("admin")),
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
