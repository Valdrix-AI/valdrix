import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.modules.billing.api.v1.billing import (
    get_public_plans,
    create_checkout,
    handle_webhook,
    get_subscription,
    get_features,
    cancel_subscription,
    update_exchange_rate,
    get_exchange_rate,
    update_pricing_plan,
)
from app.models.pricing import PricingPlan, ExchangeRate
from app.modules.billing.domain.billing.paystack_billing import TenantSubscription
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.tenant_id = "tenant-123"
    user.email = "test@example.com"
    user.tier = PricingTier.STARTER
    return user


@pytest.mark.asyncio
async def test_get_public_plans_db_success(mock_db):
    mock_plan = PricingPlan(
        id="starter",
        name="Starter",
        price_usd=29.0,
        description="Test plan",
        display_features=["Feature 1"],
        cta_text="Start Now",
        is_popular=False,
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_plan]
    mock_db.execute.return_value = mock_result

    plans = await get_public_plans(mock_db)

    assert len(plans) == 1
    assert plans[0]["name"] == "Starter"


@pytest.mark.asyncio
async def test_get_public_plans_fallback_on_error(mock_db):
    mock_db.execute.side_effect = Exception("DB Fail")
    plans = await get_public_plans(mock_db)
    assert len(plans) > 0


@pytest.mark.asyncio
@patch("app.modules.billing.domain.billing.paystack_billing.BillingService")
@patch("app.modules.billing.api.v1.billing.settings")
async def test_create_checkout_success(
    mock_settings, mock_billing_service_class, mock_db, mock_user
):
    mock_settings.PAYSTACK_SECRET_KEY = "sk_test_123"
    mock_settings.FRONTEND_URL = "https://app.valdrix.io"
    mock_settings.CORS_ORIGINS = ["https://app.valdrix.io"]
    mock_settings.ENVIRONMENT = "development"

    checkout_req = MagicMock()
    checkout_req.tier = "starter"
    checkout_req.billing_cycle = "monthly"
    checkout_req.callback_url = None

    mock_billing = mock_billing_service_class.return_value
    mock_billing.create_checkout_session = AsyncMock(
        return_value={"url": "http://checkout.url", "reference": "ref-123"}
    )

    response = await create_checkout(MagicMock(), checkout_req, mock_user, mock_db)
    assert response["checkout_url"] == "http://checkout.url"


@pytest.mark.asyncio
@patch("app.modules.billing.domain.billing.paystack_billing.BillingService")
@patch("app.modules.billing.api.v1.billing.settings")
async def test_create_checkout_rejects_untrusted_callback(
    mock_settings, mock_billing_service_class, mock_db, mock_user
):
    mock_settings.PAYSTACK_SECRET_KEY = "sk_test_123"
    mock_settings.FRONTEND_URL = "https://app.valdrix.io"
    mock_settings.CORS_ORIGINS = ["https://app.valdrix.io"]
    mock_settings.ENVIRONMENT = "production"

    checkout_req = MagicMock()
    checkout_req.tier = "starter"
    checkout_req.billing_cycle = "monthly"
    checkout_req.callback_url = "https://evil.example.com/callback"

    with pytest.raises(HTTPException) as exc:
        await create_checkout(MagicMock(), checkout_req, mock_user, mock_db)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
@patch("app.modules.billing.domain.billing.paystack_billing.WebhookHandler")
@patch("app.modules.billing.domain.billing.webhook_retry.WebhookRetryService")
@patch("app.modules.billing.api.v1.billing.settings")
async def test_handle_webhook_success(
    mock_settings, mock_retry_class, mock_handler_class, mock_db
):
    mock_settings.ENVIRONMENT = "development"
    request = AsyncMock()
    # Mock headers as MagicMock so .get is synchronous
    request.headers = MagicMock()
    request.headers.get.side_effect = lambda k, default=None: {
        "x-paystack-signature": "valid-sig"
    }.get(k, default)
    request.client.host = "127.0.0.1"
    request.body.return_value = (
        b'{"event": "charge.success", "data": {"reference": "ref-123"}}'
    )

    mock_handler = mock_handler_class.return_value
    mock_handler.verify_signature.return_value = True
    mock_handler.handle = AsyncMock(return_value={"status": "success"})

    mock_retry = mock_retry_class.return_value
    mock_retry.store_webhook = AsyncMock(return_value=MagicMock())

    try:
        response = await handle_webhook(request, mock_db)
    except Exception:
        import traceback

        traceback.print_exc()
        raise
    assert response == {"status": "success"}


@pytest.mark.asyncio
async def test_get_subscription_success(mock_db, mock_user):
    mock_sub = TenantSubscription(
        tenant_id=mock_user.tenant_id, tier="pro", status="active"
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sub
    mock_db.execute.return_value = mock_result

    response = await get_subscription(MagicMock(), mock_user, mock_db)
    assert response.tier == "pro"


@pytest.mark.asyncio
async def test_get_features(mock_user):
    with patch("app.shared.core.pricing.get_tier_config") as mock_get_config:
        mock_get_config.return_value = {"features": ["f1"], "limits": {}}
        response = await get_features(MagicMock(), mock_user)
        assert "f1" in response["features"]


@pytest.mark.asyncio
@patch("app.modules.billing.domain.billing.paystack_billing.BillingService")
async def test_cancel_subscription_success(
    mock_billing_service_class, mock_db, mock_user
):
    mock_billing = mock_billing_service_class.return_value
    mock_billing.cancel_subscription = AsyncMock()
    response = await cancel_subscription(mock_user, mock_db)
    assert response == {"status": "cancelled"}


@pytest.mark.asyncio
async def test_update_exchange_rate(mock_db, mock_user):
    req = MagicMock()
    req.rate = 1500.0
    req.provider = "manual"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await update_exchange_rate(req, mock_user, mock_db)
    assert response["rate"] == 1500.0
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_exchange_rate(mock_db, mock_user):
    from datetime import datetime

    mock_rate = ExchangeRate(
        from_currency="USD",
        to_currency="NGN",
        rate=1450.0,
        provider="manual",
        last_updated=datetime.now(),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_rate
    mock_db.execute.return_value = mock_result

    response = await get_exchange_rate(mock_user, mock_db)
    assert response["rate"] == 1450.0


@pytest.mark.asyncio
async def test_update_pricing_plan_success(mock_db, mock_user):
    plan_req = MagicMock()
    plan_req.price_usd = 99.0
    plan_req.features = {}
    plan_req.limits = {}

    mock_plan = PricingPlan(id="starter", price_usd=29.0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_plan
    mock_db.execute.return_value = mock_result

    response = await update_pricing_plan(
        MagicMock(), "starter", plan_req, mock_user, mock_db
    )
    assert response["status"] == "success"
    assert mock_plan.price_usd == 99.0
