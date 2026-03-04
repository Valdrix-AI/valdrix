from __future__ import annotations

from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.api.v1.settings.notifications_models import (
    JiraPolicyDiagnostics,
    NotificationSettingsResponse,
    SlackPolicyDiagnostics,
)


def to_notification_response(
    settings: NotificationSettings,
) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        slack_enabled=bool(getattr(settings, "slack_enabled", True)),
        slack_channel_override=settings.slack_channel_override,
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
        workflow_has_github_token=bool(getattr(settings, "workflow_github_token", None)),
        workflow_gitlab_enabled=bool(
            getattr(settings, "workflow_gitlab_enabled", False)
        ),
        workflow_gitlab_base_url=(
            getattr(settings, "workflow_gitlab_base_url", None) or "https://gitlab.com"
        ),
        workflow_gitlab_project_id=getattr(settings, "workflow_gitlab_project_id", None),
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


def to_slack_policy_diagnostics(
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


def to_jira_policy_diagnostics(
    remediation_settings: RemediationSettings | None,
    notification_settings: NotificationSettings | None,
    *,
    feature_allowed_by_tier: bool,
) -> JiraPolicyDiagnostics:
    policy_enabled = bool(getattr(remediation_settings, "policy_enabled", True))
    policy_notify_jira = bool(
        getattr(remediation_settings, "policy_violation_notify_jira", False)
    )
    jira_enabled = bool(
        getattr(notification_settings, "jira_enabled", False)
        if notification_settings
        else False
    )
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
