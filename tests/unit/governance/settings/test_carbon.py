import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import MagicMock
from app.main import app
from app.models.carbon_settings import CarbonSettings
from app.models.tenant import UserRole
from app.shared.core.auth import get_current_user, CurrentUser
from app.shared.core.pricing import PricingTier



@pytest.fixture
async def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    user.email = "admin@example.com"
    user.role = UserRole.ADMIN
    user.tier = PricingTier.PRO
    return user


@pytest.fixture(autouse=True)
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_carbon_settings_creates_default(
    async_client: AsyncClient, db_session
):
    """Test that GET /api/v1/settings/carbon creates default settings if none exist."""
    response = await async_client.get("/api/v1/settings/carbon")
    assert response.status_code == 200
    data = response.json()
    assert data["carbon_budget_kg"] == 100.0
    assert data["alert_threshold_percent"] == 80
    assert data["default_region"] == "us-east-1"

    # Verify in DB
    result = await db_session.execute(select(CarbonSettings))
    settings = result.scalars().all()
    assert len(settings) == 1
    assert settings[0].carbon_budget_kg == 100.0


@pytest.mark.asyncio
async def test_update_carbon_settings(async_client: AsyncClient, db_session, mock_user):
    """Test PUT /api/v1/settings/carbon updates existing settings."""
    # First create settings
    settings = CarbonSettings(
        tenant_id=mock_user.tenant_id,
        carbon_budget_kg=50.0,
        alert_threshold_percent=50,
        default_region="eu-west-1",
    )
    db_session.add(settings)
    await db_session.commit()

    update_data = {
        "carbon_budget_kg": 200.0,
        "alert_threshold_percent": 90,
        "default_region": "us-west-2",
        "email_enabled": True,
        "email_recipients": "alerts@example.com",
    }

    response = await async_client.put("/api/v1/settings/carbon", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["carbon_budget_kg"] == 200.0
    assert data["alert_threshold_percent"] == 90
    assert data["default_region"] == "us-west-2"
    assert data["email_enabled"] is True

    # Verify DB update
    await db_session.refresh(settings)
    assert settings.carbon_budget_kg == 200.0


@pytest.mark.asyncio
async def test_update_carbon_settings_creates_if_missing(
    async_client: AsyncClient, db_session
):
    """Test PUT /api/v1/settings/carbon creates settings if they don't exist yet."""
    update_data = {
        "carbon_budget_kg": 150.0,
        "alert_threshold_percent": 75,
        "default_region": "ap-southeast-1",
    }

    response = await async_client.put("/api/v1/settings/carbon", json=update_data)
    assert response.status_code == 200
    assert response.json()["carbon_budget_kg"] == 150.0

    result = await db_session.execute(select(CarbonSettings))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_update_carbon_settings_requires_admin(async_client: AsyncClient, app):
    """PUT /carbon should reject non-admin users."""
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="member@carbon.io",
        role=UserRole.MEMBER,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/carbon",
            json={"carbon_budget_kg": 50.0, "alert_threshold_percent": 50},
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_carbon_settings_validation_failure(
    async_client: AsyncClient, app
):
    """Reject invalid thresholds."""
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@carbon.io",
        role=UserRole.ADMIN,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/carbon",
            json={"carbon_budget_kg": -1.0, "alert_threshold_percent": 120},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_carbon_settings_invalid_email_recipients(
    async_client: AsyncClient, app
):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@carbon.io",
        role=UserRole.ADMIN,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/carbon",
            json={
                "carbon_budget_kg": 100.0,
                "alert_threshold_percent": 80,
                "default_region": "us-east-1",
                "email_enabled": True,
                "email_recipients": "not-an-email",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_carbon_settings_requires_recipients_when_enabled(
    async_client: AsyncClient, app
):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@carbon.io",
        role=UserRole.ADMIN,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/carbon",
            json={
                "carbon_budget_kg": 100.0,
                "alert_threshold_percent": 80,
                "default_region": "us-east-1",
                "email_enabled": True,
                "email_recipients": None,
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
