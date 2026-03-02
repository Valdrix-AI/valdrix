import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
from app.main import app
from app.shared.core.pricing import PricingTier
from app.models.pricing import PricingPlan, ExchangeRate
from app.shared.core.auth import get_current_user, CurrentUser
from app.shared.db.session import get_db
from app.models.tenant import UserRole
from app.shared.core.currency import ExchangeRateUnavailableError
from uuid import uuid4
from types import SimpleNamespace

transport = ASGITransport(app=app)


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db


@pytest.fixture
def mock_user():
    user = MagicMock(spec=CurrentUser)
    user.id = uuid4()
    user.tenant_id = uuid4()
    user.email = "test@example.com"
    user.role = UserRole.MEMBER
    user.tier = PricingTier.STARTER
    return user


@pytest.fixture(autouse=True)
def override_deps(mock_user, mock_db):
    async def override_get_current_user(request: Request):
        # Set state expected by auth_limit and other middleware
        request.state.tenant_id = mock_user.tenant_id
        request.state.user_id = mock_user.id
        request.state.tier = mock_user.tier
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = lambda: mock_db
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


# --- Plan Tests ---


@pytest.mark.asyncio
async def test_get_public_plans_from_db(mock_db):
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": "plan_1",
            "name": "Starter",
            "price_usd": 10.0,
            "description": "Test",
            "display_features": [],
            "cta_text": "CTA",
            "is_popular": False,
        }
    ]
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/plans")
    assert response.status_code == 200
    assert response.json()[0]["price_monthly"] == 10.0


@pytest.mark.asyncio
async def test_get_public_plans_fallback(mock_db):
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/plans")
    assert response.status_code == 200
    assert len(response.json()) >= 3


@pytest.mark.asyncio
async def test_get_public_plans_db_error(mock_db):
    mock_db.execute.side_effect = Exception("DB Fail")
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/plans")
    assert response.status_code == 200


# --- Subscription Tests ---


@pytest.mark.asyncio
async def test_get_subscription_trial(mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/subscription")
    assert response.json()["tier"] == "free"


@pytest.mark.asyncio
async def test_get_subscription_error(mock_db):
    mock_db.execute.side_effect = Exception("General Fail")
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/subscription")
    assert response.status_code == 500


# --- Feature Tests ---


@pytest.mark.asyncio
async def test_get_features():
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/features")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_billing_usage_exposes_connection_counts_and_limits(
    mock_db, mock_user
):
    mock_user.tier = PricingTier.PRO

    async def execute_side_effect(statement, *args, **kwargs):
        sql = str(statement)
        assert "aws_connections" in sql
        assert "azure_connections" in sql
        assert "gcp_connections" in sql
        assert "saas_connections" in sql
        assert "license_connections" in sql
        result = MagicMock()
        result.all.return_value = [
            SimpleNamespace(provider="aws", connected=2),
            SimpleNamespace(provider="azure", connected=1),
            SimpleNamespace(provider="gcp", connected=0),
            SimpleNamespace(provider="saas", connected=3),
            SimpleNamespace(provider="license", connected=0),
        ]
        return result

    mock_db.execute.side_effect = execute_side_effect

    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tier"] == PricingTier.PRO.value
    assert payload["connections"]["aws"]["connected"] == 2
    assert payload["connections"]["aws"]["limit"] == 25
    assert payload["connections"]["saas"]["connected"] == 3
    assert payload["connections"]["saas"]["limit"] == 10


# --- Checkout Tests ---


@pytest.mark.asyncio
async def test_create_checkout_success(mock_db):
    with (
        patch("app.modules.billing.api.v1.billing.settings") as mock_settings,
        patch(
            "app.modules.billing.domain.billing.paystack_billing.BillingService"
        ) as mock_service_cls,
    ):
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test"
        mock_settings.FRONTEND_URL = "https://app"
        mock_service = mock_service_cls.return_value
        mock_service.create_checkout_session = AsyncMock(
            return_value={"url": "https://url", "reference": "ref"}
        )
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_checkout_no_tenant(mock_user):
    mock_user.tenant_id = None
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test"
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_checkout_error(mock_db):
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test"
        mock_settings.FRONTEND_URL = "https://app.valdrics.test"
        mock_settings.CORS_ORIGINS = ["https://app.valdrics.test"]
        mock_settings.ENVIRONMENT = "development"
        with patch(
            "app.modules.billing.domain.billing.paystack_billing.BillingService"
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_checkout_session.side_effect = Exception(
                "Checkout Fail"
            )
            async with AsyncClient(transport=transport, base_url="https://test") as ac:
                response = await ac.post(
                    "/api/v1/billing/checkout", json={"tier": "pro"}
                )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_create_checkout_rate_unavailable_returns_503(mock_db):
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test"
        mock_settings.FRONTEND_URL = "https://app.valdrics.test"
        mock_settings.CORS_ORIGINS = ["https://app.valdrics.test"]
        mock_settings.ENVIRONMENT = "development"
        with patch(
            "app.modules.billing.domain.billing.paystack_billing.BillingService"
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_checkout_session.side_effect = (
                ExchangeRateUnavailableError("rate stale")
            )
            async with AsyncClient(transport=transport, base_url="https://test") as ac:
                response = await ac.post(
                    "/api/v1/billing/checkout", json={"tier": "pro"}
                )
    assert response.status_code == 503


# --- Cancellation Tests ---


@pytest.mark.asyncio
async def test_cancel_subscription_success(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    with patch(
        "app.modules.billing.domain.billing.paystack_billing.BillingService"
    ) as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.cancel_subscription = AsyncMock()
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post("/api/v1/billing/cancel")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cancel_subscription_no_tenant(mock_user):
    mock_user.role = UserRole.ADMIN
    mock_user.tenant_id = None
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/cancel")
    assert response.status_code == 400


# --- Exchange Rate Tests ---


@pytest.mark.asyncio
async def test_update_exchange_rate_new(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/admin/rates", json={"rate": 1500.0})
    assert response.status_code == 200
    mock_db.add.assert_called()


@pytest.mark.asyncio
async def test_update_exchange_rate_update(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    rate = MagicMock(spec=ExchangeRate)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = rate
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/admin/rates", json={"rate": 1500.0})
    assert response.status_code == 200
    assert rate.rate == 1500.0


@pytest.mark.asyncio
async def test_get_exchange_rate_not_found(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/admin/rates")
    assert response.status_code == 200
    assert response.json()["provider"] == "unavailable"
    assert response.json()["rate"] is None
    assert response.json()["billing_safe"] is False
    assert "warning" in response.json()


@pytest.mark.asyncio
async def test_get_exchange_rate_non_official_provider_flags_unsafe(mock_db, mock_user):
    from datetime import datetime, timezone

    mock_user.role = UserRole.ADMIN
    rate = MagicMock(spec=ExchangeRate)
    rate.rate = 1500.0
    rate.provider = "manual"
    rate.last_updated = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = rate
    mock_db.execute.return_value = mock_result

    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/admin/rates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_official_provider"] is False
    assert payload["billing_safe"] is False
    assert payload["warning"] is not None


@pytest.mark.asyncio
async def test_get_exchange_rate_stale_official_provider_flags_unsafe(
    mock_db, mock_user
):
    from datetime import datetime, timedelta, timezone

    mock_user.role = UserRole.ADMIN
    rate = MagicMock(spec=ExchangeRate)
    rate.rate = 1500.0
    rate.provider = "cbn_nfem"
    rate.last_updated = datetime.now(timezone.utc) - timedelta(hours=25)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = rate
    mock_db.execute.return_value = mock_result

    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/admin/rates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_official_provider"] is True
    assert payload["is_stale"] is True
    assert payload["billing_safe"] is False
    assert payload["warning"] is not None


# --- Pricing Plan Admin Tests ---


@pytest.mark.asyncio
async def test_update_pricing_plan_success(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    plan = MagicMock(spec=PricingPlan)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = plan
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post(
            "/api/v1/billing/admin/plans/starter",
            json={"price_usd": 15.0, "limits": {"l1": 10}},
        )
    assert response.status_code == 200
    assert plan.price_usd == 15.0


@pytest.mark.asyncio
async def test_update_pricing_plan_not_found(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post(
            "/api/v1/billing/admin/plans/invalid", json={"price_usd": 15.0}
        )
    assert response.status_code == 404


# --- Webhook Tests ---


@pytest.mark.asyncio
async def test_handle_webhook_no_signature():
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/webhook")
    assert response.status_code in (
        401,
        403,
        415,
        422,
    )  # Header validation may hit first


@pytest.mark.asyncio
async def test_handle_webhook_processing_error(mock_db):
    payload = {"event": "charge.success", "data": {"reference": "ref_123"}}
    with (
        patch(
            "app.modules.billing.domain.billing.paystack_billing.WebhookHandler"
        ) as mock_handler_cls,
        patch(
            "app.modules.billing.domain.billing.webhook_retry.WebhookRetryService"
        ) as mock_retry_cls,
    ):
        mock_handler = mock_handler_cls.return_value
        mock_handler.verify_signature.return_value = True
        mock_handler.handle.side_effect = Exception("Process Error")
        mock_retry = mock_retry_cls.return_value
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_retry.store_webhook = AsyncMock(return_value=mock_job)
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post(
                "/api/v1/billing/webhook",
                json=payload,
                headers={"X-Paystack-Signature": "valid"},
            )
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_handle_webhook_unauthorized_ip():
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "production"
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post(
                "/api/v1/billing/webhook", headers={"X-Forwarded-For": "1.2.3.4"}
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_handle_webhook_unauthorized_ip_staging():
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "staging"
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post(
                "/api/v1/billing/webhook", headers={"X-Forwarded-For": "1.2.3.4"}
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_handle_webhook_rightmost_forwarded_ip_is_used():
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "production"
        mock_settings.TRUST_PROXY_HEADERS = True
        mock_settings.TRUSTED_PROXY_HOPS = 1
        mock_settings.TRUSTED_PROXY_CIDRS = ["0.0.0.0/0", "::/0"]
        mock_settings.PAYSTACK_WEBHOOK_ALLOWED_IPS = ["52.31.139.75"]
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post(
                "/api/v1/billing/webhook",
                json={"event": "charge.success", "data": {"reference": "ref_123"}},
                headers={
                    "X-Forwarded-For": "1.2.3.4, 52.31.139.75",
                    "Content-Type": "application/json",
                },
            )
    assert response.status_code != 403
