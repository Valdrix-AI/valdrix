import pytest
import uuid
from httpx import AsyncClient
from app.models.notification_settings import NotificationSettings
from unittest.mock import AsyncMock, patch
from app.shared.core.auth import CurrentUser, get_current_user, UserRole

@pytest.mark.asyncio
async def test_get_notification_settings_creates_default(async_client: AsyncClient, mock_user_id, mock_tenant_id, app):
    """GET /notifications should create default settings if they don't exist."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
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
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
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
async def test_test_slack_notification(async_client: AsyncClient, mock_user_id, mock_tenant_id, app):
    """POST /notifications/test-slack should trigger SlackService."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
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
