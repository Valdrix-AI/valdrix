from __future__ import annotations

from collections.abc import Callable
from typing import Any


def enforce_incident_integrations_access(
    *,
    data: Any,
    current_tier: Any,
    normalize_tier_fn: Callable[[Any], Any],
    is_feature_enabled_fn: Callable[[Any, Any], bool],
    incident_integrations_feature: Any,
    raise_http_exception_fn: Callable[[int, str], None],
) -> None:
    needs_incident_integrations = bool(
        getattr(data, "jira_enabled", False)
        or getattr(data, "teams_enabled", False)
        or getattr(data, "workflow_github_enabled", False)
        or getattr(data, "workflow_gitlab_enabled", False)
        or getattr(data, "workflow_webhook_enabled", False)
    )
    if not needs_incident_integrations:
        return

    tier = normalize_tier_fn(current_tier)
    if is_feature_enabled_fn(tier, incident_integrations_feature):
        return

    raise_http_exception_fn(
        403,
        (
            f"Feature '{incident_integrations_feature.value}' requires an upgrade. "
            f"Current tier: {tier.value}"
        ),
    )


def build_notification_settings_create_kwargs(
    *,
    data: Any,
    tenant_id: Any,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "slack_enabled": data.slack_enabled,
        "slack_channel_override": data.slack_channel_override,
        "jira_enabled": data.jira_enabled,
        "jira_base_url": data.jira_base_url,
        "jira_email": str(data.jira_email) if data.jira_email else None,
        "jira_project_key": data.jira_project_key,
        "jira_issue_type": data.jira_issue_type,
        "jira_api_token": data.jira_api_token,
        "teams_enabled": data.teams_enabled,
        "teams_webhook_url": data.teams_webhook_url,
        "digest_schedule": data.digest_schedule,
        "digest_hour": data.digest_hour,
        "digest_minute": data.digest_minute,
        "alert_on_budget_warning": data.alert_on_budget_warning,
        "alert_on_budget_exceeded": data.alert_on_budget_exceeded,
        "alert_on_zombie_detected": data.alert_on_zombie_detected,
        "workflow_github_enabled": data.workflow_github_enabled,
        "workflow_github_owner": data.workflow_github_owner,
        "workflow_github_repo": data.workflow_github_repo,
        "workflow_github_workflow_id": data.workflow_github_workflow_id,
        "workflow_github_ref": data.workflow_github_ref,
        "workflow_github_token": data.workflow_github_token,
        "workflow_gitlab_enabled": data.workflow_gitlab_enabled,
        "workflow_gitlab_base_url": data.workflow_gitlab_base_url,
        "workflow_gitlab_project_id": data.workflow_gitlab_project_id,
        "workflow_gitlab_ref": data.workflow_gitlab_ref,
        "workflow_gitlab_trigger_token": data.workflow_gitlab_trigger_token,
        "workflow_webhook_enabled": data.workflow_webhook_enabled,
        "workflow_webhook_url": data.workflow_webhook_url,
        "workflow_webhook_bearer_token": data.workflow_webhook_bearer_token,
    }


def apply_notification_settings_update(
    *,
    settings: Any,
    updates: dict[str, Any],
) -> None:
    settings.slack_enabled = updates["slack_enabled"]
    settings.slack_channel_override = updates["slack_channel_override"]
    settings.jira_enabled = updates["jira_enabled"]
    settings.jira_base_url = updates["jira_base_url"]
    settings.jira_email = str(updates["jira_email"]) if updates["jira_email"] else None
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
        settings.workflow_gitlab_trigger_token = updates["workflow_gitlab_trigger_token"]
    elif updates["clear_workflow_gitlab_trigger_token"]:
        settings.workflow_gitlab_trigger_token = None

    settings.workflow_webhook_enabled = updates["workflow_webhook_enabled"]
    settings.workflow_webhook_url = updates["workflow_webhook_url"]
    if updates["workflow_webhook_bearer_token"]:
        settings.workflow_webhook_bearer_token = updates["workflow_webhook_bearer_token"]
    elif updates["clear_workflow_webhook_bearer_token"]:
        settings.workflow_webhook_bearer_token = None


def validate_notification_settings_requirements(
    *,
    settings: Any,
    raise_http_exception_fn: Callable[[int, str], None],
) -> None:
    if settings.jira_enabled:
        jira_requirements = [
            ("jira_base_url", settings.jira_base_url),
            ("jira_email", settings.jira_email),
            ("jira_project_key", settings.jira_project_key),
            ("jira_api_token", settings.jira_api_token),
        ]
        missing = [name for name, value in jira_requirements if not value]
        if missing:
            raise_http_exception_fn(
                422,
                "Jira is enabled but missing required fields: " + ", ".join(missing),
            )
    if settings.teams_enabled and not settings.teams_webhook_url:
        raise_http_exception_fn(
            422,
            "Teams is enabled but missing required field: teams_webhook_url",
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
            raise_http_exception_fn(
                422,
                "GitHub workflow dispatch is enabled but missing required fields: "
                + ", ".join(missing),
            )

    if settings.workflow_gitlab_enabled:
        gitlab_requirements = [
            ("workflow_gitlab_base_url", settings.workflow_gitlab_base_url),
            ("workflow_gitlab_project_id", settings.workflow_gitlab_project_id),
            ("workflow_gitlab_trigger_token", settings.workflow_gitlab_trigger_token),
        ]
        missing = [name for name, value in gitlab_requirements if not value]
        if missing:
            raise_http_exception_fn(
                422,
                "GitLab workflow dispatch is enabled but missing required fields: "
                + ", ".join(missing),
            )

    if settings.workflow_webhook_enabled and not settings.workflow_webhook_url:
        raise_http_exception_fn(
            422,
            "Webhook workflow dispatch is enabled but missing required field: "
            "workflow_webhook_url",
        )


def build_notification_settings_audit_payload(settings: Any) -> dict[str, Any]:
    return {
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
    }
