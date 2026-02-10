import pytest
import uuid
from httpx import AsyncClient
from app.models.notification_settings import NotificationSettings
from unittest.mock import AsyncMock, patch
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.config import Settings

@pytest.mark.asyncio
async def test_get_notification_settings_creates_default(async_client: AsyncClient, mock_user_id, mock_tenant_id, app):
    """GET /notifications should create default settings if they don't exist."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/notifications")
        assert response.status_code == 200
        data = response.json()
        assert data["slack_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_notification_settings(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """PUT /notifications should update existing settings."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    settings = NotificationSettings(tenant_id=tenant_id, slack_enabled=True, digest_schedule="daily")
    db.add(settings)
    await db.commit()
    
    update_data = {"slack_enabled": False, "digest_schedule": "weekly"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put("/api/v1/settings/notifications", json=update_data)
        assert response.status_code == 200
        assert response.json()["slack_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_notification_settings_creates_if_missing(async_client: AsyncClient, db, app):
    """PUT /notifications should create settings when missing."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="creator@valdrix.io", role=UserRole.ADMIN)

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
        response = await async_client.put("/api/v1/settings/notifications", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["slack_channel_override"] == "#alerts"
        assert data["digest_schedule"] == "weekly"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_test_slack_notification(async_client: AsyncClient, mock_user_id, mock_tenant_id, app):
    """POST /notifications/test-slack should trigger SlackService."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    from app.shared.core.config import Settings
    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"
    
    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    # Patch where the lazy-imported service is DEFINED/USED
    with patch("app.shared.core.config.get_settings", return_value=mock_settings), \
         patch("app.modules.notifications.domain.SlackService", return_value=mock_slack):
        
        try:
            response = await async_client.post("/api/v1/settings/notifications/test-slack")
            assert response.status_code == 200
            assert response.json()["status"] == "success"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_test_slack_notification_missing_config(async_client: AsyncClient, app):
    """POST /notifications/test-slack returns 400 when Slack config missing."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = None
    mock_settings.SLACK_CHANNEL_ID = None

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("app.shared.core.config.get_settings", return_value=mock_settings):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 400
        assert "Slack is not configured" in response.json()["error"]
    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_test_slack_notification_uses_override(async_client: AsyncClient, db, app):
    """POST /notifications/test-slack uses channel override when present."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    db.add(NotificationSettings(
        tenant_id=tenant_id,
        slack_enabled=True,
        slack_channel_override="#override-channel",
        digest_schedule="daily",
        digest_hour=9,
        digest_minute=0,
        alert_on_budget_warning=True,
        alert_on_budget_exceeded=True,
        alert_on_zombie_detected=True,
    ))
    await db.commit()

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"

    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("app.shared.core.config.get_settings", return_value=mock_settings), \
         patch("app.modules.notifications.domain.SlackService", return_value=mock_slack) as slack_class:
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 200
        slack_class.assert_called_once_with("xoxb-test", "#override-channel")
    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_test_slack_notification_failure_and_exception(async_client: AsyncClient, app):
    """POST /notifications/test-slack handles Slack failure and exceptions."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"

    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Failure branch (send_alert returns False)
    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = False
    with patch("app.shared.core.config.get_settings", return_value=mock_settings), \
         patch("app.modules.notifications.domain.SlackService", return_value=mock_slack):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 500
        assert "Failed to send Slack notification" in response.json()["error"]

    # Exception branch
    mock_slack = AsyncMock()
    mock_slack.send_alert.side_effect = Exception("boom")
    with patch("app.shared.core.config.get_settings", return_value=mock_settings), \
         patch("app.modules.notifications.domain.SlackService", return_value=mock_slack):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 500
        assert "Slack test failed" in response.json()["error"]

    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_notifications_requires_admin(async_client: AsyncClient, app):
    member = CurrentUser(id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="member@notify.io", role=UserRole.MEMBER)
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
    member = CurrentUser(id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="member@notify.io", role=UserRole.MEMBER)
    app.dependency_overrides[get_current_user] = lambda: member
    try:
        response = await async_client.post("/api/v1/settings/notifications/test-slack")
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_notification_settings_validation_failure(async_client: AsyncClient, app):
    admin = CurrentUser(id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="admin@notify.io", role=UserRole.ADMIN)
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
