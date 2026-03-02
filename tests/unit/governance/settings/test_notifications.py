import pytest
import uuid
from httpx import AsyncClient
from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings
from unittest.mock import AsyncMock, patch
from app.modules.governance.api.v1.settings.notifications import (
    NotificationSettingsUpdate,
)
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.config import Settings
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_get_notification_settings_creates_default(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    """GET /notifications should create default settings if they don't exist."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/notifications")
        assert response.status_code == 200
        data = response.json()
        assert data["slack_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings(
    async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app
):
    """PUT /notifications should update existing settings."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    settings = NotificationSettings(
        tenant_id=tenant_id, slack_enabled=True, digest_schedule="daily"
    )
    db.add(settings)
    await db.commit()

    update_data = {"slack_enabled": False, "digest_schedule": "weekly"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications", json=update_data
        )
        assert response.status_code == 200
        assert response.json()["slack_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_creates_if_missing(
    async_client: AsyncClient, db, app
):
    """PUT /notifications should create settings when missing."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="creator@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        update_data = {
            "slack_enabled": True,
            "slack_channel_override": "#alerts",
            "digest_schedule": "weekly",
            "digest_hour": 7,
            "digest_minute": 15,
            "alert_on_budget_warning": False,
            "alert_on_budget_exceeded": True,
            "alert_on_zombie_detected": False,
        }
        response = await async_client.put(
            "/api/v1/settings/notifications", json=update_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["slack_channel_override"] == "#alerts"
        assert data["digest_schedule"] == "weekly"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_slack_notification(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    """POST /notifications/test-slack should trigger SlackService."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new=AsyncMock(return_value=mock_slack),
    ):
        try:
            response = await async_client.post(
                "/api/v1/settings/notifications/test-slack"
            )
            assert response.status_code == 200
            assert response.json()["status"] == "success"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_slack_notification_missing_config(async_client: AsyncClient, app):
    """POST /notifications/test-slack returns 400 when Slack config missing."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="admin@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new=AsyncMock(return_value=None),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 400
        assert "Slack is not configured" in response.json()["error"]
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_slack_notification_uses_override(
    async_client: AsyncClient, db, app
):
    """POST /notifications/test-slack uses tenant-scoped Slack service."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="admin@valdrics.io", role=UserRole.ADMIN
    )

    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            slack_channel_override="#override-channel",
            digest_schedule="daily",
            digest_hour=9,
            digest_minute=0,
            alert_on_budget_warning=True,
            alert_on_budget_exceeded=True,
            alert_on_zombie_detected=True,
        )
    )
    await db.commit()

    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new=AsyncMock(return_value=mock_slack),
    ) as mock_get_tenant:
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 200
        mock_get_tenant.assert_awaited_once_with(db, tenant_id)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_slack_notification_failure_and_exception(
    async_client: AsyncClient, app
):
    """POST /notifications/test-slack handles Slack failure and exceptions."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="admin@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Failure branch (send_alert returns False)
    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = False
    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new=AsyncMock(return_value=mock_slack),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 500
        assert "Failed to send Slack notification" in response.json()["error"]

    # Exception branch
    mock_slack = AsyncMock()
    mock_slack.send_alert.side_effect = Exception("boom")
    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new=AsyncMock(return_value=mock_slack),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 500
        assert "Slack test failed" in response.json()["error"]

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notifications_requires_admin(async_client: AsyncClient, app):
    member = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="member@notify.io",
        role=UserRole.MEMBER,
    )
    app.dependency_overrides[get_current_user] = lambda: member
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={"slack_enabled": True, "digest_schedule": "daily"},
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_slack_notification_requires_admin(async_client: AsyncClient, app):
    member = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="member@notify.io",
        role=UserRole.MEMBER,
    )
    app.dependency_overrides[get_current_user] = lambda: member
    try:
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_validation_failure(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "slack_channel_override": "invalid!",
                "digest_schedule": "monthly",
                "digest_hour": 25,
                "digest_minute": 70,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_with_jira_config(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "slack_channel_override": "#ops",
                "jira_enabled": True,
                "jira_base_url": "https://example.atlassian.net",
                "jira_email": "jira@example.com",
                "jira_project_key": "FINOPS",
                "jira_issue_type": "Task",
                "jira_api_token": "jira_token_value_123",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["jira_enabled"] is True
        assert data["jira_project_key"] == "FINOPS"
        assert data["has_jira_api_token"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_jira_requires_incident_tier(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": True,
                "jira_base_url": "https://example.atlassian.net",
                "jira_email": "jira@example.com",
                "jira_project_key": "FINOPS",
                "jira_issue_type": "Task",
                "jira_api_token": "jira_token_value_123",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 403
        assert "incident_integrations" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_teams_requires_incident_tier(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "teams_enabled": True,
                "teams_webhook_url": "https://example.webhook.office.com/webhookb2/xxxx",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 403
        assert "incident_integrations" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_teams_missing_fields_returns_422(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "teams_enabled": True,
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 422
        assert "teams_webhook_url" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_teams_notification_success(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    mock_teams = AsyncMock()
    mock_teams.send_alert.return_value = True
    with patch(
        "app.modules.notifications.domain.get_tenant_teams_service",
        new=AsyncMock(return_value=mock_teams),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_teams_notification_missing_config(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    with patch(
        "app.modules.notifications.domain.get_tenant_teams_service",
        new=AsyncMock(return_value=None),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")
        assert response.status_code == 400
        assert "Teams is not configured" in response.json()["error"]
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_teams_notification_requires_incident_tier(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    response = await async_client.post("/api/v1/settings/notifications/test-teams")
    assert response.status_code == 403
    assert "incident_integrations" in response.json()["error"]
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_teams_notification_failure_and_exception(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin

    mock_teams = AsyncMock()
    mock_teams.send_alert.return_value = False
    with patch(
        "app.modules.notifications.domain.get_tenant_teams_service",
        new=AsyncMock(return_value=mock_teams),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")
        assert response.status_code == 500
        assert "Failed to send Teams notification" in response.json()["error"]

    mock_teams = AsyncMock()
    mock_teams.send_alert.side_effect = Exception("teams boom")
    with patch(
        "app.modules.notifications.domain.get_tenant_teams_service",
        new=AsyncMock(return_value=mock_teams),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")
        assert response.status_code == 500
        assert "Teams test failed" in response.json()["error"]

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_jira_notification_success(async_client: AsyncClient, db, app):
    tenant_id = uuid.uuid4()
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    await db.commit()

    mock_jira = AsyncMock()
    mock_jira.create_issue.return_value = True
    app.dependency_overrides[get_current_user] = lambda: admin
    with patch(
        "app.modules.notifications.domain.jira.JiraService", return_value=mock_jira
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_jira_notification_missing_config(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.post("/api/v1/settings/notifications/test-jira")
        assert response.status_code == 400
        assert "Jira is not configured" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_notification_settings_update_rejects_token_and_clear_flag() -> None:
    with pytest.raises(
        ValueError, match="Provide jira_api_token or clear_jira_api_token"
    ):
        _ = NotificationSettingsUpdate(
            jira_api_token="jira_token_value_123",
            clear_jira_api_token=True,
        )
    with pytest.raises(
        ValueError, match="Provide teams_webhook_url or clear_teams_webhook_url"
    ):
        _ = NotificationSettingsUpdate(
            teams_webhook_url="https://example.webhook.office.com/abc",
            clear_teams_webhook_url=True,
        )
    with pytest.raises(
        ValueError, match="Provide workflow_github_token or clear_workflow_github_token"
    ):
        _ = NotificationSettingsUpdate(
            workflow_github_token="gh_token_value_123",
            clear_workflow_github_token=True,
        )
    with pytest.raises(
        ValueError,
        match="Provide workflow_gitlab_trigger_token or clear_workflow_gitlab_trigger_token",
    ):
        _ = NotificationSettingsUpdate(
            workflow_gitlab_trigger_token="gl_token_value_123",
            clear_workflow_gitlab_trigger_token=True,
        )
    with pytest.raises(
        ValueError,
        match="Provide workflow_webhook_bearer_token or clear_workflow_webhook_bearer_token",
    ):
        _ = NotificationSettingsUpdate(
            workflow_webhook_bearer_token="webhook_token_value_123",
            clear_workflow_webhook_bearer_token=True,
        )


@pytest.mark.asyncio
async def test_update_notification_settings_clear_jira_token(
    async_client: AsyncClient, db, app
):
    tenant_id = uuid.uuid4()
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            jira_enabled=False,
            jira_api_token="jira_token_value_123",
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": False,
                "clear_jira_api_token": True,
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["has_jira_api_token"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_jira_missing_fields_returns_422(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": True,
                "jira_base_url": "https://example.atlassian.net",
                "jira_project_key": "FINOPS",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 422
        assert "missing required fields" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_jira_notification_requires_tenant(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=None,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.post("/api/v1/settings/notifications/test-jira")
        assert response.status_code == 403
        assert "Tenant context required" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_jira_notification_failure_and_exception(
    async_client: AsyncClient, db, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin

    mock_jira = AsyncMock()
    mock_jira.create_issue.return_value = False
    with patch(
        "app.modules.notifications.domain.get_tenant_jira_service",
        return_value=mock_jira,
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")
        assert response.status_code == 500
        assert "Failed to create Jira test issue" in response.json()["error"]

    mock_jira = AsyncMock()
    mock_jira.create_issue.side_effect = Exception("jira boom")
    with patch(
        "app.modules.notifications.domain.get_tenant_jira_service",
        return_value=mock_jira,
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")
        assert response.status_code == 500
        assert "Jira test failed" in response.json()["error"]

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_missing_config(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        mock_settings = Settings()
        mock_settings.SLACK_BOT_TOKEN = None
        mock_settings.SLACK_CHANNEL_ID = None
        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            response = await async_client.get(
                "/api/v1/settings/notifications/policy-diagnostics"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["has_activeops_settings"] is False
        assert data["has_notification_settings"] is False
        assert data["slack"]["ready"] is False
        assert "missing_slack_bot_token" in data["slack"]["reasons"]
        assert "missing_slack_channel_target" in data["slack"]["reasons"]
        assert data["jira"]["ready"] is False
        assert "tenant_jira_disabled" in data["jira"]["reasons"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_ready(
    async_client: AsyncClient, db, app
):
    tenant_id = uuid.uuid4()
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            slack_channel_override="#finops-alerts",
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    db.add(
        RemediationSettings(
            tenant_id=tenant_id,
            policy_enabled=True,
            policy_violation_notify_slack=True,
            policy_violation_notify_jira=True,
        )
    )
    await db.commit()

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            response = await async_client.get(
                "/api/v1/settings/notifications/policy-diagnostics"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["policy_enabled"] is True
        assert data["slack"]["ready"] is True
        assert data["slack"]["channel_source"] == "tenant_override"
        assert data["jira"]["ready"] is True
        assert data["jira"]["feature_allowed_by_tier"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_jira_tier_blocked(
    async_client: AsyncClient, db, app
):
    tenant_id = uuid.uuid4()
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    db.add(
        RemediationSettings(
            tenant_id=tenant_id,
            policy_enabled=True,
            policy_violation_notify_jira=True,
        )
    )
    await db.commit()

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            response = await async_client.get(
                "/api/v1/settings/notifications/policy-diagnostics"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["jira"]["ready"] is False
        assert data["jira"]["feature_allowed_by_tier"] is False
        assert "tier_missing_incident_integrations_feature" in data["jira"]["reasons"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_with_workflow_config(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": False,
                "workflow_github_enabled": True,
                "workflow_github_owner": "Valdrics-AI",
                "workflow_github_repo": "valdrics",
                "workflow_github_workflow_id": "remediation.yml",
                "workflow_github_ref": "main",
                "workflow_github_token": "gh_token_value_123",
                "workflow_gitlab_enabled": True,
                "workflow_gitlab_base_url": "https://gitlab.com",
                "workflow_gitlab_project_id": "12345",
                "workflow_gitlab_ref": "main",
                "workflow_gitlab_trigger_token": "gl_token_value_123",
                "workflow_webhook_enabled": True,
                "workflow_webhook_url": "https://ci.example.com/hooks/valdrics",
                "workflow_webhook_bearer_token": "webhook_token_value_123",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_github_enabled"] is True
        assert data["workflow_has_github_token"] is True
        assert data["workflow_gitlab_enabled"] is True
        assert data["workflow_has_gitlab_trigger_token"] is True
        assert data["workflow_webhook_enabled"] is True
        assert data["workflow_has_webhook_bearer_token"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_workflow_requires_incident_tier(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": False,
                "workflow_github_enabled": True,
                "workflow_github_owner": "Valdrics-AI",
                "workflow_github_repo": "valdrics",
                "workflow_github_workflow_id": "remediation.yml",
                "workflow_github_ref": "main",
                "workflow_github_token": "gh_token_value_123",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 403
        assert "incident_integrations" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_notification_settings_workflow_missing_fields_returns_422(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "jira_enabled": False,
                "workflow_github_enabled": True,
                "workflow_github_owner": "Valdrics-AI",
                "workflow_github_repo": "valdrics",
                "workflow_github_ref": "main",
                "digest_schedule": "daily",
                "digest_hour": 9,
                "digest_minute": 0,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )
        assert response.status_code == 422
        assert "missing required fields" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_workflow_notification_success(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    workflow_dispatcher = AsyncMock()
    workflow_dispatcher.dispatch.return_value = True
    try:
        with patch(
            "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
            new=AsyncMock(return_value=[workflow_dispatcher]),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-workflow"
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_test_workflow_notification_missing_config(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with patch(
            "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
            new=AsyncMock(return_value=[]),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-workflow"
            )
        assert response.status_code == 400
        assert "No workflow integration is configured" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_capture_notification_acceptance_evidence_success(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    slack = AsyncMock()
    slack.send_alert.return_value = True
    jira = AsyncMock()
    jira.create_issue.return_value = True
    teams = AsyncMock()
    teams.send_alert.return_value = True
    dispatcher = AsyncMock()
    dispatcher.provider = "github_actions"
    dispatcher.dispatch.return_value = True
    try:
        with (
            patch(
                "app.modules.notifications.domain.get_tenant_slack_service",
                new=AsyncMock(return_value=slack),
            ),
            patch(
                "app.modules.notifications.domain.get_tenant_jira_service",
                new=AsyncMock(return_value=jira),
            ),
            patch(
                "app.modules.notifications.domain.get_tenant_teams_service",
                new=AsyncMock(return_value=teams),
            ),
            patch(
                "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[dispatcher]),
            ),
        ):
            capture = await async_client.post(
                "/api/v1/settings/notifications/acceptance-evidence/capture",
                json={},
            )
            assert capture.status_code == 200
            payload = capture.json()
            assert payload["overall_status"] == "success"
            assert payload["passed"] == 4
            assert payload["failed"] == 0
            run_id = payload["run_id"]

            listing = await async_client.get(
                "/api/v1/settings/notifications/acceptance-evidence",
                params={"run_id": run_id},
            )
            assert listing.status_code == 200
            list_payload = listing.json()
            assert list_payload["total"] == 5
            channels = {item["channel"] for item in list_payload["items"]}
            assert {"slack", "jira", "teams", "workflow", "suite"} <= channels
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_capture_notification_acceptance_evidence_partial_failure_fail_fast(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ):
            capture = await async_client.post(
                "/api/v1/settings/notifications/acceptance-evidence/capture",
                json={
                    "include_slack": True,
                    "include_jira": True,
                    "include_teams": True,
                    "include_workflow": True,
                    "fail_fast": True,
                },
            )
            assert capture.status_code == 200
            payload = capture.json()
            assert payload["overall_status"] == "failed"
            assert payload["passed"] == 0
            assert payload["failed"] == 1
            assert len(payload["results"]) == 1
            assert payload["results"][0]["channel"] == "slack"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_notification_acceptance_evidence_requires_tenant(
    async_client: AsyncClient, app
):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=None,
        email="admin@notify.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.get(
            "/api/v1/settings/notifications/acceptance-evidence"
        )
        assert response.status_code == 403
        assert "Tenant context required" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
