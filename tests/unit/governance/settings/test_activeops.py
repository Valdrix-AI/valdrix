import pytest
import uuid
from httpx import AsyncClient
from app.models.remediation_settings import RemediationSettings
from app.shared.core.auth import CurrentUser, get_current_user, UserRole

@pytest.mark.asyncio
async def test_get_activeops_settings_creates_default(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """GET /activeops should create default settings if they don't exist."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/activeops")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_pilot_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_get_activeops_settings_creates_default_for_new_tenant(async_client: AsyncClient, db, app):
    """Ensure GET /activeops creates defaults for a fresh tenant."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="fresh@valdrix.io", role=UserRole.ADMIN)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/activeops")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_pilot_enabled"] is False
        assert data["min_confidence_threshold"] == 0.95
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_activeops_settings(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """PUT /activeops should update existing settings."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    settings = RemediationSettings(tenant_id=tenant_id, auto_pilot_enabled=False, min_confidence_threshold=0.95)
    db.add(settings)
    await db.commit()
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put("/api/v1/settings/activeops", json={"auto_pilot_enabled": True, "min_confidence_threshold": 0.90})
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
