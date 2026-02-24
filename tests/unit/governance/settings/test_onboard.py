import pytest
import uuid
from uuid import UUID
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from app.main import app
from app.models.tenant import Tenant, User
from app.shared.core.auth import get_current_user_from_jwt


@pytest.fixture
def mock_jwt_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "newuser@example.com"
    return user


@pytest.fixture(autouse=True)
def override_auth(mock_jwt_user):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_jwt_user
    yield
    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_success(async_client: AsyncClient, db_session, mock_jwt_user):
    """Test successful onboarding creates tenant and user."""
    onboard_data = {"tenant_name": "Test Tenant", "admin_email": "admin@example.com"}

    response = await async_client.post("/api/v1/settings/onboard", json=onboard_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "onboarded"
    tenant_id = data["tenant_id"]

    # Verify Tenant
    result = await db_session.execute(
        select(Tenant).where(Tenant.id == UUID(tenant_id))
    )
    tenant = result.scalar_one()
    assert tenant.name == "Test Tenant"

    # Verify User
    result = await db_session.execute(select(User).where(User.id == mock_jwt_user.id))
    db_user = result.scalar_one()
    assert db_user.tenant_id == UUID(tenant_id)
    assert db_user.email == mock_jwt_user.email


@pytest.mark.asyncio
async def test_onboard_already_onboarded(
    async_client: AsyncClient, db_session, mock_jwt_user
):
    """Test that onboarding fails if user already exists in DB."""
    # Pre-create user
    tenant = Tenant(name="Existing")
    db_session.add(tenant)
    await db_session.flush()
    user = User(id=mock_jwt_user.id, email=mock_jwt_user.email, tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()

    onboard_data = {"tenant_name": "New Tenant"}
    response = await async_client.post("/api/v1/settings/onboard", json=onboard_data)
    assert response.status_code == 400
    assert "Already onboarded" in response.json()["error"]


@pytest.mark.asyncio
async def test_onboard_with_cloud_verification_success(async_client: AsyncClient):
    """Test onboarding with successful AWS connection verification."""
    onboard_data = {
        "tenant_name": "Cloud Tenant",
        "cloud_config": {
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/ValdrixRole",
            "external_id": "ext-123",
        },
    }

    # Mock AdapterFactory and AWSAdapter
    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.verify_connection.return_value = True
        mock_get_adapter.return_value = mock_adapter

        response = await async_client.post(
            "/api/v1/settings/onboard", json=onboard_data
        )
        assert response.status_code == 200
        assert response.json()["status"] == "onboarded"
        mock_adapter.verify_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_onboard_with_cloud_verification_failure(async_client: AsyncClient):
    """Test onboarding fails if cloud connection verification fails."""
    onboard_data = {
        "tenant_name": "Bad Cloud Tenant",
        "cloud_config": {
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/BadRole",
        },
    }

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter"
    ) as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.verify_connection.return_value = False
        mock_get_adapter.return_value = mock_adapter

        response = await async_client.post(
            "/api/v1/settings/onboard", json=onboard_data
        )
        assert response.status_code == 400
        assert "Cloud connection verification failed" in response.json()["error"]


@pytest.mark.asyncio
async def test_onboard_rejects_http_cloud_credentials_in_production(
    async_client: AsyncClient,
):
    onboard_data = {
        "tenant_name": "Secure Tenant",
        "cloud_config": {
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/ValdrixRole",
            "external_id": "ext-123",
        },
    }

    with patch(
        "app.modules.governance.api.v1.settings.onboard.get_settings"
    ) as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.ENVIRONMENT = "production"
        mock_get_settings.return_value = mock_settings

        response = await async_client.post(
            "/api/v1/settings/onboard", json=onboard_data
        )
        assert response.status_code == 400
        assert "HTTPS is required" in response.json()["error"]


def _turnstile_strict_settings() -> SimpleNamespace:
    return SimpleNamespace(
        TURNSTILE_ENABLED=True,
        TURNSTILE_ENFORCE_IN_TESTING=True,
        TURNSTILE_SECRET_KEY="turnstile-secret-key",
        TURNSTILE_VERIFY_URL="https://challenges.cloudflare.com/turnstile/v0/siteverify",
        TURNSTILE_TIMEOUT_SECONDS=2.0,
        TURNSTILE_FAIL_OPEN=False,
        TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT=True,
        TURNSTILE_REQUIRE_SSO_DISCOVERY=True,
        TURNSTILE_REQUIRE_ONBOARD=True,
        TESTING=True,
        ENVIRONMENT="test",
    )


@pytest.mark.asyncio
async def test_onboard_requires_turnstile_token(async_client: AsyncClient):
    with patch(
        "app.shared.core.turnstile.get_settings",
        return_value=_turnstile_strict_settings(),
    ):
        response = await async_client.post(
            "/api/v1/settings/onboard",
            json={"tenant_name": "Needs Turnstile"},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "turnstile_token_required"


@pytest.mark.asyncio
async def test_onboard_rejects_invalid_turnstile(async_client: AsyncClient):
    with (
        patch(
            "app.shared.core.turnstile.get_settings",
            return_value=_turnstile_strict_settings(),
        ),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            return_value={"success": False, "error-codes": ["invalid-input-response"]},
        ),
    ):
        response = await async_client.post(
            "/api/v1/settings/onboard",
            json={"tenant_name": "Needs Turnstile"},
            headers={"X-Turnstile-Token": "invalid-token"},
        )
    assert response.status_code == 403
    assert response.json()["error"] == "turnstile_verification_failed"
