import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.shared.core.auth import CurrentUser, get_current_user_from_jwt, UserRole
from app.models.tenant import User


@pytest.fixture
def mock_user():
    user_id = uuid.uuid4()
    return CurrentUser(
        id=user_id,
        tenant_id=None,
        email=f"onboard_{uuid.uuid4().hex[:8]}@test.io",
        role=UserRole.MEMBER,
    )


@pytest.mark.asyncio
async def test_onboard_lifecycle(async_client: AsyncClient, db, app):
    """Deep test for the Onboarding API using real DB fixture."""
    user_id = uuid.uuid4()
    email = f"onboard_{uuid.uuid4().hex[:8]}@test.io"
    mock_user = CurrentUser(
        id=user_id, tenant_id=None, email=email, role=UserRole.MEMBER
    )

    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    try:
        onboard_data = {"tenant_name": "Test Tenant Corp", "admin_email": email}
        response = await async_client.post(
            "/api/v1/settings/onboard", json=onboard_data
        )
        assert response.status_code == 200
        assert response.json()["status"] == "onboarded"
        generated_tenant_id = response.json()["tenant_id"]

        response = await async_client.post(
            "/api/v1/settings/onboard", json=onboard_data
        )
        assert response.status_code == 400

        result = await db.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()
        assert db_user is not None
        assert str(db_user.tenant_id) == generated_tenant_id

    finally:
        app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_endpoint(async_client: AsyncClient, app, mock_user):
    # Using real DB or mock? Lifecycle uses real, this one can use real too for consistency
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    response = await async_client.post(
        "/api/v1/settings/onboard", json={"tenant_name": "TestTenant"}
    )
    assert response.status_code == 200
    assert "tenant_id" in response.json()

    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_duplicate(async_client: AsyncClient, app, mock_user):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    # First onboarding
    await async_client.post(
        "/api/v1/settings/onboard", json={"tenant_name": "DuplicateTenant"}
    )

    # Second onboarding
    response = await async_client.post(
        "/api/v1/settings/onboard", json={"tenant_name": "DuplicateTenant"}
    )
    assert response.status_code == 400
    data = response.json()
    assert "Already onboarded" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_with_cloud_config_multi(
    async_client: AsyncClient, app, mock_user
):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    platforms = [
        ("aws", {"role_arn": "arn:aws:iam::...", "external_id": "123"}),
        (
            "azure",
            {
                "client_id": "...",
                "client_secret": "...",
                "azure_tenant_id": "...",
                "subscription_id": "...",
            },
        ),
        ("gcp", {"project_id": "...", "service_account_json": "{}"}),
        (
            "saas",
            {
                "vendor": "stripe",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 9.5,
                    }
                ],
            },
        ),
        (
            "license",
            {
                "vendor": "microsoft_365",
                "auth_method": "manual",
                "license_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 4.2,
                    }
                ],
            },
        ),
        (
            "platform",
            {
                "vendor": "datadog",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 14.1,
                    }
                ],
            },
        ),
        (
            "hybrid",
            {
                "vendor": "vmware",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 17.8,
                    }
                ],
            },
        ),
    ]

    for platform, config in platforms:
        mock_adapter = AsyncMock()
        mock_adapter.verify_connection.return_value = True

        with patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            return_value=mock_adapter,
        ):
            payload = {
                "tenant_name": f"Tenant-{platform}",
                "cloud_config": {"platform": platform, **config},
            }
            # Need fresh user ID per attempt to avoid "Already onboarded"
            fresh_user = CurrentUser(
                id=uuid.uuid4(),
                tenant_id=None,
                email=f"{platform}@test.ai",
                role=UserRole.MEMBER,
            )
            app.dependency_overrides[get_current_user_from_jwt] = lambda: fresh_user

            response = await async_client.post("/api/v1/settings/onboard", json=payload)
            assert response.status_code == 200, (
                f"Failed for {platform}: {response.json()}"
            )

    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_invalid_platform(async_client: AsyncClient, app, mock_user):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    payload = {"tenant_name": "NewTenant", "cloud_config": {"platform": "unknown"}}
    response = await async_client.post("/api/v1/settings/onboard", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "Unsupported platform" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_connection_fail(async_client: AsyncClient, app, mock_user):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = False

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter",
        return_value=mock_adapter,
    ):
        payload = {
            "tenant_name": "FailTenant",
            "cloud_config": {"platform": "aws", "role_arn": "arn:aws:iam::..."},
        }
        response = await async_client.post("/api/v1/settings/onboard", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "verification failed" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.pop(get_current_user_from_jwt, None)


@pytest.mark.asyncio
async def test_onboard_exception_handler(async_client: AsyncClient, app, mock_user):
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter",
        side_effect=Exception("Unexpected crash"),
    ):
        payload = {
            "tenant_name": "CrashTenant",
            "cloud_config": {"platform": "aws", "role_arn": "arn:aws:iam::..."},
        }
        response = await async_client.post("/api/v1/settings/onboard", json=payload)
        assert response.status_code == 400
        assert "Unexpected crash" in str(response.json())

    app.dependency_overrides.pop(get_current_user_from_jwt, None)
