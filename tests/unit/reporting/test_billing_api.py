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
from uuid import uuid4

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
    plan = MagicMock(spec=PricingPlan)
    plan.id = "plan_1"
    plan.name = "Starter"
    plan.price_usd = 10.0
    plan.description = "Test"
    plan.display_features = []
    plan.cta_text = "CTA"
    plan.is_popular = False
    plan.is_active = True
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [plan]
    mock_db.execute.return_value = mock_result 
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.get("/api/v1/billing/plans")
    assert response.status_code == 200
    assert response.json()[0]["price_monthly"] == 10.0

@pytest.mark.asyncio
async def test_get_public_plans_fallback(mock_db):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
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
    assert response.json()["tier"] == "free_trial"

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

# --- Checkout Tests ---

@pytest.mark.asyncio
async def test_create_checkout_success(mock_db):
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings, \
         patch("app.modules.billing.domain.billing.paystack_billing.BillingService") as mock_service_cls:
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test"
        mock_settings.FRONTEND_URL = "https://app"
        mock_service = mock_service_cls.return_value
        mock_service.create_checkout_session = AsyncMock(return_value={"url": "https://url", "reference": "ref"})
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
        mock_settings.FRONTEND_URL = "https://app.valdrix.test"
        mock_settings.CORS_ORIGINS = ["https://app.valdrix.test"]
        mock_settings.ENVIRONMENT = "development"
        with patch("app.modules.billing.domain.billing.paystack_billing.BillingService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_checkout_session.side_effect = Exception("Checkout Fail")
            async with AsyncClient(transport=transport, base_url="https://test") as ac:
                response = await ac.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 500

# --- Cancellation Tests ---

@pytest.mark.asyncio
async def test_cancel_subscription_success(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    with patch("app.modules.billing.domain.billing.paystack_billing.BillingService") as mock_service_cls:
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
    assert response.json()["provider"] == "fallback"

# --- Pricing Plan Admin Tests ---

@pytest.mark.asyncio
async def test_update_pricing_plan_success(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    plan = MagicMock(spec=PricingPlan)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = plan
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/admin/plans/starter", json={"price_usd": 15.0, "limits": {"l1": 10}})
    assert response.status_code == 200
    assert plan.price_usd == 15.0

@pytest.mark.asyncio
async def test_update_pricing_plan_not_found(mock_db, mock_user):
    mock_user.role = UserRole.ADMIN
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/admin/plans/invalid", json={"price_usd": 15.0})
    assert response.status_code == 404

# --- Webhook Tests ---

@pytest.mark.asyncio
async def test_handle_webhook_no_signature():
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        response = await ac.post("/api/v1/billing/webhook")
    assert response.status_code in (401, 403, 422) # Fastapi validation might hit first

@pytest.mark.asyncio
async def test_handle_webhook_processing_error(mock_db):
    payload = {"event": "charge.success", "data": {"reference": "ref_123"}}
    with patch("app.modules.billing.domain.billing.paystack_billing.WebhookHandler") as mock_handler_cls, \
         patch("app.modules.billing.domain.billing.webhook_retry.WebhookRetryService") as mock_retry_cls:
        mock_handler = mock_handler_cls.return_value
        mock_handler.verify_signature.return_value = True
        mock_handler.handle.side_effect = Exception("Process Error")
        mock_retry = mock_retry_cls.return_value
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_retry.store_webhook = AsyncMock(return_value=mock_job)
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post("/api/v1/billing/webhook", json=payload, headers={"X-Paystack-Signature": "valid"})
    assert response.json()["status"] == "queued"

@pytest.mark.asyncio
async def test_handle_webhook_unauthorized_ip():
    with patch("app.modules.billing.api.v1.billing.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "production"
        async with AsyncClient(transport=transport, base_url="https://test") as ac:
            response = await ac.post("/api/v1/billing/webhook", headers={"X-Forwarded-For": "1.2.3.4"})
    assert response.status_code == 403
