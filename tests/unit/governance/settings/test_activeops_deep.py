import pytest
import uuid
from httpx import AsyncClient
from app.models.remediation_settings import RemediationSettings
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from sqlalchemy import select

@pytest.mark.asyncio
async def test_activeops_settings_full_lifecycle(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """Deep test for ActiveOps settings covering all branches."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@activeops.io", role=UserRole.ADMIN)
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    try:
        # 1. GET - Should create default (Missing lines 57-72)
        response = await async_client.get("/api/v1/settings/activeops")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_pilot_enabled"] is False
        assert data["min_confidence_threshold"] == 0.95
        
        # Verify in DB
        result = await db.execute(select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id))
        db_settings = result.scalar_one()
        assert db_settings.auto_pilot_enabled is False
        
        # 2. GET - Should return existing (Missing lines 57-72 branch)
        response = await async_client.get("/api/v1/settings/activeops")
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is False
        
        # 3. PUT - Update existing (Missing lines 89-118)
        update_data = {"auto_pilot_enabled": True, "min_confidence_threshold": 0.85}
        response = await async_client.put("/api/v1/settings/activeops", json=update_data)
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is True
        assert response.json()["min_confidence_threshold"] == 0.85
        
        # 4. PUT - Update with different values to hit remaining update logic
        update_data = {"auto_pilot_enabled": False, "min_confidence_threshold": 0.99}
        response = await async_client.put("/api/v1/settings/activeops", json=update_data)
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is False
        assert response.json()["min_confidence_threshold"] == 0.99

    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_activeops_settings_creates_if_missing(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """PUT /activeops should create settings if they don't exist (edge case)."""
    user_id = uuid.UUID(str(mock_user_id))
    # Use a fresh tenant ID to ensure settings don't exist
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test-new@activeops.io", role=UserRole.ADMIN)
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        update_data = {"auto_pilot_enabled": True, "min_confidence_threshold": 0.75}
        response = await async_client.put("/api/v1/settings/activeops", json=update_data)
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is True
        assert response.json()["min_confidence_threshold"] == 0.75
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_activeops_requires_admin(async_client: AsyncClient, app):
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="member@activeops.io", role=UserRole.MEMBER)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/activeops",
            json={"auto_pilot_enabled": True, "min_confidence_threshold": 0.9},
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_activeops_validation_failure(async_client: AsyncClient, app, mock_user_id):
    """Reject invalid confidence thresholds."""
    tenant_id = uuid.uuid4()
    user_id = uuid.UUID(str(mock_user_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@activeops.io", role=UserRole.ADMIN)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/activeops",
            json={"auto_pilot_enabled": True, "min_confidence_threshold": 0.1},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
