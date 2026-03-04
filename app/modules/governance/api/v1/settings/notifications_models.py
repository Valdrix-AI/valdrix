"""Pydantic models for notification settings and acceptance evidence APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    digest_schedule: str
    digest_hour: int
    digest_minute: int
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
    channel_source: str


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
        description="GitLab base URL (HTTPS)",
    )
    workflow_gitlab_project_id: str | None = Field(
        None, max_length=128, description="GitLab project ID"
    )
    workflow_gitlab_ref: str = Field(
        "main", max_length=100, description="GitLab ref/branch"
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
        False, description="Enable generic webhook workflow dispatch"
    )
    workflow_webhook_url: str | None = Field(
        None,
        max_length=1024,
        pattern=r"^https://",
        description="Webhook endpoint URL (HTTPS)",
    )
    workflow_webhook_bearer_token: str | None = Field(
        None,
        min_length=8,
        max_length=1024,
        description="Optional webhook bearer token. Leave empty to keep current token.",
    )
    clear_workflow_webhook_bearer_token: bool = Field(
        False, description="Clear stored webhook bearer token"
    )

    @model_validator(mode="after")
    def validate_clear_token_flags(self) -> "NotificationSettingsUpdate":
        if self.jira_api_token and self.clear_jira_api_token:
            raise ValueError(
                "Provide jira_api_token or clear_jira_api_token=true, not both."
            )
        if self.teams_webhook_url and self.clear_teams_webhook_url:
            raise ValueError(
                "Provide teams_webhook_url or clear_teams_webhook_url=true, not both."
            )
        if self.workflow_github_token and self.clear_workflow_github_token:
            raise ValueError(
                "Provide workflow_github_token or clear_workflow_github_token=true, not both."
            )
        if (
            self.workflow_gitlab_trigger_token
            and self.clear_workflow_gitlab_trigger_token
        ):
            raise ValueError(
                "Provide workflow_gitlab_trigger_token or clear_workflow_gitlab_trigger_token=true, not both."
            )
        if (
            self.workflow_webhook_bearer_token
            and self.clear_workflow_webhook_bearer_token
        ):
            raise ValueError(
                "Provide workflow_webhook_bearer_token or clear_workflow_webhook_bearer_token=true, not both."
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
