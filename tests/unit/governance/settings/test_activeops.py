import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from app.models.remediation_settings import RemediationSettings
from app.models.tenant import UserRole
from app.shared.core.auth import CurrentUser, get_current_user



@pytest.mark.asyncio
async def test_get_activeops_settings_creates_default(
    async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app
):
    """GET /activeops should create default settings if they don't exist."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/activeops")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_pilot_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_activeops_settings_creates_default_for_new_tenant(
    async_client: AsyncClient, db, app
):
    """Ensure GET /activeops creates defaults for a fresh tenant."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="fresh@valdrics.io", role=UserRole.ADMIN
    )

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
async def test_update_activeops_settings(
    async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app
):
    """PUT /activeops should update existing settings."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    settings = RemediationSettings(
        tenant_id=tenant_id, auto_pilot_enabled=False, min_confidence_threshold=0.95
    )
    db.add(settings)
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/activeops",
            json={"auto_pilot_enabled": True, "min_confidence_threshold": 0.90},
        )
        assert response.status_code == 200
        assert response.json()["auto_pilot_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_reactivate_hard_cap_endpoint(async_client: AsyncClient, app):
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="admin@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch(
            "app.modules.governance.api.v1.settings.activeops.BudgetHardCapService"
        ) as service_cls:
            service = MagicMock()
            service.reverse_hard_cap = AsyncMock(return_value=4)
            service_cls.return_value = service

            response = await async_client.post(
                "/api/v1/settings/activeops/hard-cap/reactivate",
                json={"reason": "false-positive budget spike"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "status": "reactivated",
            "restored_connections": 4,
        }
        service.reverse_hard_cap.assert_awaited_once_with(
            tenant_id,
            actor_id=user_id,
            reason="false-positive budget spike",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_reactivate_hard_cap_endpoint_returns_not_found(
    async_client: AsyncClient, app
):
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="admin@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch(
            "app.modules.governance.api.v1.settings.activeops.BudgetHardCapService"
        ) as service_cls:
            service = MagicMock()
            service.reverse_hard_cap = AsyncMock(
                side_effect=ValueError("No hard-cap snapshot available for tenant")
            )
            service_cls.return_value = service

            response = await async_client.post(
                "/api/v1/settings/activeops/hard-cap/reactivate",
                json={"reason": "operator override"},
            )

        assert response.status_code == 404
        payload = response.json()
        detail = payload.get("detail")
        if detail is None and isinstance(payload.get("error"), dict):
            detail = payload["error"].get("message")
        if detail is None:
            detail = str(payload)
        assert "No hard-cap snapshot available for tenant" in detail
    finally:
        app.dependency_overrides.pop(get_current_user, None)
