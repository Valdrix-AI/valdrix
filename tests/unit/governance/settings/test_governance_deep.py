import pytest
import uuid
from httpx import AsyncClient
from app.shared.core.auth import CurrentUser, get_current_user, UserRole

@pytest.mark.asyncio
async def test_carbon_settings_lifecycle(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """Deep test for Carbon settings."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@carbon.io", role=UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    try:
        # 1. GET - Create default
        response = await async_client.get("/api/v1/settings/carbon")
        assert response.status_code == 200
        assert response.json()["carbon_budget_kg"] == 100.0
        
        # 2. PUT - Update
        update_data = {"carbon_budget_kg": 200.0, "alert_threshold_percent": 90}
        response = await async_client.put("/api/v1/settings/carbon", json=update_data)
        assert response.status_code == 200
        assert response.json()["carbon_budget_kg"] == 200.0
        assert response.json()["alert_threshold_percent"] == 90
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_notifications_settings_lifecycle(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """Deep test for Notification settings."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@notify.io", role=UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    try:
        # 1. GET - Create default
        response = await async_client.get("/api/v1/settings/notifications")
        assert response.status_code == 200
        assert response.json()["slack_enabled"] is True
        
        # 2. PUT - Update
        update_data = {"slack_enabled": False, "digest_schedule": "weekly"}
        response = await async_client.put("/api/v1/settings/notifications", json=update_data)
        assert response.status_code == 200
        assert response.json()["slack_enabled"] is False
        assert response.json()["digest_schedule"] == "weekly"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_connections_settings_lifecycle(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """Deep test for Connections settings (Setup templates)."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@conns.io", role=UserRole.ADMIN)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    try:
        # Check AWS setup templates
        response = await async_client.post("/api/v1/settings/connections/aws/setup")
        assert response.status_code == 200
        assert "cloudformation_yaml" in response.json()
        
        # Check Azure setup snippet
        response = await async_client.post("/api/v1/settings/connections/azure/setup")
        assert response.status_code == 200
        
        # Check GCP setup snippet
        response = await async_client.post("/api/v1/settings/connections/gcp/setup")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
