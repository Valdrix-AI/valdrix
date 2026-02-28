from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.modules.billing.domain.billing.paystack_billing as billing_mod
from app.modules.billing.domain.billing.paystack_billing import (
    BillingService,
    PaystackClient,
    WebhookHandler,
)
from app.shared.core.pricing import PricingTier, TIER_CONFIG

STARTER_MONTHLY_USD = float(TIER_CONFIG[PricingTier.STARTER]["price_usd"]["monthly"])
STARTER_MONTHLY_SUBUNITS = int(round(STARTER_MONTHLY_USD * 100))


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def configured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_SECRET_KEY", "sk_test_key", raising=False
    )
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_PLAN_STARTER", "PLN_STARTER", raising=False
    )
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_PLAN_GROWTH", "PLN_GROWTH", raising=False
    )
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_PLAN_PRO", "PLN_PRO", raising=False
    )
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_PLAN_ENTERPRISE", "PLN_ENT", raising=False
    )


def test_email_hash_normalizes_and_truncates() -> None:
    assert billing_mod.email_hash(None) is None
    digest = billing_mod.email_hash("  USER@Example.COM ")
    assert digest is not None
    assert len(digest) == 12
    assert digest == billing_mod.email_hash("user@example.com")


@pytest.mark.asyncio
async def test_paystack_request_rejects_non_dict_payload(
    configured_settings: None,
) -> None:
    client = PaystackClient()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = ["not", "a", "dict"]

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=mock_response)):
        with pytest.raises(ValueError, match="Invalid Paystack response payload type"):
            await client._request("GET", "transaction/verify/ref")


@pytest.mark.asyncio
async def test_initialize_transaction_includes_plan_code(
    configured_settings: None,
) -> None:
    client = PaystackClient()
    with patch.object(
        client, "_request", new=AsyncMock(return_value={"status": True})
    ) as mock_req:
        await client.initialize_transaction(
            email="user@example.com",
            amount_kobo=1000,
            plan_code="PLN_123",
            callback_url="https://callback.example.com",
            metadata={"tenant_id": "t1"},
        )
    assert mock_req.await_args is not None
    payload = mock_req.await_args.args[2]
    assert payload["plan"] == "PLN_123"


@pytest.mark.asyncio
async def test_client_wrapper_methods_delegate_request(
    configured_settings: None,
) -> None:
    client = PaystackClient()
    with patch.object(
        client, "_request", new=AsyncMock(return_value={"status": True})
    ) as mock_req:
        await client.charge_authorization("u@example.com", 100, "AUTH", {"x": 1})
        await client.verify_transaction("REF123")
        await client.fetch_subscription("SUB123")
        await client.disable_subscription("SUB123", "TOK123")

    called_endpoints = [call.args[1] for call in mock_req.await_args_list]
    assert "transaction/charge_authorization" in called_endpoints
    assert "transaction/verify/REF123" in called_endpoints
    assert "subscription/SUB123" in called_endpoints
    assert "subscription/disable" in called_endpoints


@pytest.mark.asyncio
async def test_billing_service_init_ignores_legacy_amount_config(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    invalid_config = {
        PricingTier.STARTER: {"paystack_amount_kobo": "bad-type"},
        PricingTier.GROWTH: {
            "paystack_amount_kobo": {"monthly": "bad", "annual": 1200}
        },
    }
    with (
        patch("app.shared.core.pricing.TIER_CONFIG", invalid_config),
        patch.object(billing_mod.logger, "warning") as mock_warning,
    ):
        service = BillingService(mock_db)
    assert service._resolve_plan_code(
        tier=PricingTier.STARTER, billing_cycle="monthly"
    ) == "PLN_STARTER"
    # Plan-code resolution no longer depends on eager amount map parsing.
    mock_warning.assert_not_called()


@pytest.mark.asyncio
async def test_create_checkout_session_uses_fixed_plan_code_when_available(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    fx_runtime = MagicMock()
    fx_runtime.get_ngn_rate = AsyncMock(return_value=1500.0)
    fx_runtime.convert_usd_to_ngn.return_value = 150000
    service = BillingService(
        mock_db, exchange_rate_service_factory=lambda _db: fx_runtime
    )
    mock_db.execute.return_value = _scalar_result(None)
    service.client.initialize_transaction = AsyncMock(
        return_value={
            "data": {
                "authorization_url": "https://pay.example/checkout",
                "reference": "REFNGN1",
            }
        }
    )

    await service.create_checkout_session(
        tenant_id=uuid4(),
        tier=PricingTier.STARTER,
        email="user@example.com",
        callback_url="https://callback.example.com",
        billing_cycle="monthly",
        currency="NGN",
    )

    fx_runtime.get_ngn_rate.assert_awaited_once()
    assert service.client.initialize_transaction.await_args is not None
    init_kwargs = service.client.initialize_transaction.await_args.kwargs
    assert init_kwargs["plan_code"] == "PLN_STARTER"
    assert init_kwargs["metadata"]["plan_code"] == "PLN_STARTER"
    assert init_kwargs["metadata"]["pricing_mode"] == "fixed_plan_code"


@pytest.mark.asyncio
async def test_create_checkout_session_falls_back_to_dynamic_mode_without_plan_code(
    mock_db: MagicMock,
    configured_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_PLAN_STARTER", None, raising=False
    )
    fx_runtime = MagicMock()
    fx_runtime.get_ngn_rate = AsyncMock(return_value=1500.0)
    fx_runtime.convert_usd_to_ngn.return_value = 150000
    service = BillingService(
        mock_db, exchange_rate_service_factory=lambda _db: fx_runtime
    )
    mock_db.execute.return_value = _scalar_result(None)
    service.client.initialize_transaction = AsyncMock(
        return_value={
            "data": {
                "authorization_url": "https://pay.example/checkout",
                "reference": "REFNGN2",
            }
        }
    )

    await service.create_checkout_session(
        tenant_id=uuid4(),
        tier=PricingTier.STARTER,
        email="user@example.com",
        callback_url="https://callback.example.com",
        billing_cycle="monthly",
        currency="NGN",
    )

    assert service.client.initialize_transaction.await_args is not None
    init_kwargs = service.client.initialize_transaction.await_args.kwargs
    assert init_kwargs["plan_code"] is None
    assert init_kwargs["metadata"]["plan_code"] is None
    assert init_kwargs["metadata"]["pricing_mode"] == "dynamic_amount"


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_tier_raises(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    with patch("app.modules.billing.domain.billing.paystack_service_impl.PaystackClient"):
        service = BillingService(mock_db)
    with patch("app.shared.core.pricing.TIER_CONFIG", {}):
        with pytest.raises(ValueError, match="Invalid tier"):
            await service.create_checkout_session(
                tenant_id=uuid4(),
                tier=PricingTier.STARTER,
                email="a@b.com",
                callback_url="https://callback",
            )


@pytest.mark.asyncio
async def test_create_checkout_session_logs_and_reraises(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    with patch(
        "app.modules.billing.domain.billing.paystack_service_impl.PaystackClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.initialize_transaction = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        service = BillingService(mock_db)
    with (
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(return_value=1500.0),
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=150000,
        ),
        patch.object(billing_mod.logger, "error") as mock_error,
    ):
        mock_db.execute.return_value = _scalar_result(None)
        with pytest.raises(RuntimeError, match="boom"):
            await service.create_checkout_session(
                uuid4(), PricingTier.STARTER, "u@e.com", "https://callback"
            )
    assert mock_error.called


@pytest.mark.asyncio
async def test_charge_renewal_returns_false_when_auth_decryption_fails(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc", tenant_id=uuid4(), tier=PricingTier.STARTER.value
    )
    with patch(
        "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
        return_value=None,
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_charge_renewal_invalid_tier_value_returns_false(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(paystack_auth_code="enc", tenant_id=uuid4(), tier="not-a-tier")
    mock_db.execute.return_value = _scalar_result(None)
    with patch(
        "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
        return_value="AUTH",
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_charge_renewal_missing_tier_config_returns_false(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc", tenant_id=uuid4(), tier=PricingTier.STARTER.value
    )
    mock_db.execute.return_value = _scalar_result(None)
    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch("app.shared.core.pricing.TIER_CONFIG", {}),
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_charge_renewal_missing_user_returns_false(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc", tenant_id=uuid4(), tier=PricingTier.STARTER.value
    )
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=10.0)),
        _scalar_result(None),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(return_value=1500.0),
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=150000,
        ),
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_charge_renewal_email_decrypt_failure_returns_false(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc", tenant_id=uuid4(), tier=PricingTier.STARTER.value
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=10.0)),
        _scalar_result(mock_user),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(return_value=1500.0),
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=150000,
        ),
        patch("app.shared.core.security.decrypt_string", return_value=None),
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_charge_renewal_charge_exception_returns_false(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc", tenant_id=uuid4(), tier=PricingTier.STARTER.value
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=10.0)),
        _scalar_result(mock_user),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(return_value=1500.0),
        ),
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=150000,
        ),
        patch(
            "app.shared.core.security.decrypt_string", return_value="user@example.com"
        ),
        patch.object(
            service.client,
            "charge_authorization",
            new=AsyncMock(side_effect=RuntimeError("paystack down")),
        ),
    ):
        assert await service.charge_renewal(sub) is False


@pytest.mark.asyncio
async def test_cancel_subscription_raises_when_no_active_subscription(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    mock_db.execute.return_value = _scalar_result(None)
    with pytest.raises(ValueError, match="No active subscription to cancel"):
        await service.cancel_subscription(uuid4())


@pytest.mark.asyncio
async def test_cancel_subscription_reraises_disable_failure(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(paystack_subscription_code="SUB", paystack_email_token="TOK")
    mock_db.execute.return_value = _scalar_result(sub)
    with patch.object(
        service.client,
        "disable_subscription",
        new=AsyncMock(side_effect=RuntimeError("disable failed")),
    ):
        with pytest.raises(RuntimeError, match="disable failed"):
            await service.cancel_subscription(uuid4())


def test_verify_signature_missing_signature_or_secret(
    mock_db: MagicMock,
    configured_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = WebhookHandler(mock_db)
    payload = b'{"event":"x"}'
    assert handler.verify_signature(payload, "") is False
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_SECRET_KEY", None, raising=False
    )
    assert handler.verify_signature(payload, "abc123") is False


@pytest.mark.asyncio
async def test_handle_unknown_event_returns_success(mock_db: MagicMock) -> None:
    handler = WebhookHandler(mock_db)
    request = MagicMock()
    request.headers = {"Content-Type": "application/json"}
    payload = json.dumps({"event": "unknown.event", "data": {}}).encode()
    with patch.object(handler, "verify_signature", return_value=True):
        result = await handler.handle(request, payload, "sig")
    assert result == {"status": "success"}


@pytest.mark.asyncio
async def test_handle_subscription_create_edge_branches(mock_db: MagicMock) -> None:
    handler = WebhookHandler(mock_db)

    # Missing customer code branch
    await handler._handle_subscription_create({"subscription_code": "SUB"})
    mock_db.execute.assert_not_awaited()

    # Tenant not found branch
    mock_db.execute.return_value = _scalar_result(None)
    await handler._handle_subscription_create({"customer": {"customer_code": "CUS"}})

    # Invalid date branch
    sub = MagicMock()
    mock_db.execute.return_value = _scalar_result(sub)
    await handler._handle_subscription_create(
        {
            "customer": {"customer_code": "CUS"},
            "subscription_code": "SUB",
            "email_token": "TOK",
            "next_payment_date": "not-a-date",
        }
    )
    assert sub.paystack_subscription_code == "SUB"
    assert sub.paystack_email_token == "TOK"


@pytest.mark.asyncio
async def test_handle_charge_success_with_unusable_metadata_returns(
    mock_db: MagicMock,
) -> None:
    handler = WebhookHandler(mock_db)
    await handler._handle_charge_success(
        {
            "metadata": "{not-json",
            "customer": {},
            "reference": "REF123",
        }
    )
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_charge_success_email_fallback_paths(
    mock_db: MagicMock,
) -> None:
    handler = WebhookHandler(mock_db)
    tenant_id = uuid4()
    user = MagicMock(tenant_id=tenant_id)
    existing_sub = MagicMock(tier=PricingTier.STARTER.value)

    with (
        patch("app.shared.core.security.generate_blind_index", return_value="BIDX"),
        patch(
            "app.modules.billing.domain.billing.paystack_shared.encrypt_string",
            return_value="enc-auth",
        ),
    ):
        mock_db.execute.side_effect = [
            _scalar_result(user),
            _scalar_result(existing_sub),
        ]
        await handler._handle_charge_success(
            {
                "metadata": {},
                "customer": {"customer_code": "CUS1", "email": "u@example.com"},
                "authorization": {"authorization_code": "AUTH"},
            }
        )
    assert existing_sub.paystack_customer_code == "CUS1"
    assert existing_sub.paystack_auth_code == "enc-auth"

    # Email fallback fails -> no tenant -> return early
    mock_db.execute.reset_mock()
    mock_db.execute.side_effect = None
    with patch("app.shared.core.security.generate_blind_index", return_value="BIDX"):
        mock_db.execute.return_value = _scalar_result(None)
        await handler._handle_charge_success(
            {
                "metadata": {},
                "customer": {"customer_code": "CUS2", "email": "none@example.com"},
                "reference": "REF-NONE",
            }
        )


@pytest.mark.asyncio
async def test_handle_charge_success_creates_subscription_without_auth(
    mock_db: MagicMock,
) -> None:
    handler = WebhookHandler(mock_db)
    tenant_id = uuid4()
    mock_db.execute.return_value = _scalar_result(None)
    with patch(
        "app.modules.billing.domain.billing.paystack_webhook_impl.sync_tenant_plan",
        new=AsyncMock(),
    ) as mock_sync_tenant_plan:
        await handler._handle_charge_success(
            {
                "metadata": {"tenant_id": str(tenant_id), "tier": PricingTier.GROWTH.value},
                "customer": {"customer_code": "CUS3", "email": "x@example.com"},
                "authorization": {},
            }
        )
    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    assert any(isinstance(obj, billing_mod.TenantSubscription) for obj in added_objects)
    mock_sync_tenant_plan.assert_awaited_once()
    # Billing webhooks should also emit an immutable audit log event.
    assert any(obj.__class__.__name__ == "AuditLog" for obj in added_objects)


@pytest.mark.asyncio
async def test_subscription_disable_and_invoice_failed_edge_paths(
    mock_db: MagicMock,
) -> None:
    handler = WebhookHandler(mock_db)
    await handler._handle_subscription_disable({})
    mock_db.execute.assert_not_awaited()

    mock_db.execute.return_value = _scalar_result(None)
    await handler._handle_subscription_disable({"subscription_code": "SUB-NONE"})

    mock_db.execute.reset_mock()
    await handler._handle_invoice_failed(
        {"invoice_code": "INV1", "customer": {"customer_code": "CUS"}}
    )
    mock_db.execute.assert_not_awaited()

    mock_db.execute.return_value = _scalar_result(None)
    await handler._handle_invoice_failed({"subscription_code": "SUB-NONE"})


@pytest.mark.asyncio
async def test_create_checkout_session_usd_disabled_rejected(
    mock_db: MagicMock,
    configured_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_ENABLE_USD_CHECKOUT", False, raising=False
    )
    service = BillingService(mock_db)

    with pytest.raises(ValueError, match="USD checkout is not enabled"):
        await service.create_checkout_session(
            tenant_id=uuid4(),
            tier=PricingTier.STARTER,
            email="user@example.com",
            callback_url="https://callback.example.com",
            currency="USD",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_usd_enabled_uses_cents_without_fx_lookup(
    mock_db: MagicMock,
    configured_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        billing_mod.settings, "PAYSTACK_ENABLE_USD_CHECKOUT", True, raising=False
    )
    service = BillingService(mock_db)
    mock_db.execute.return_value = _scalar_result(None)
    service.client.initialize_transaction = AsyncMock(
        return_value={
            "data": {"authorization_url": "https://pay.example/checkout", "reference": "REFUSD1"}
        }
    )

    with (
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(),
        ) as mock_rate,
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=999999,
        ) as mock_convert,
    ):
        result = await service.create_checkout_session(
            tenant_id=uuid4(),
            tier=PricingTier.STARTER,
            email="user@example.com",
            callback_url="https://callback.example.com",
            billing_cycle="monthly",
            currency="USD",
        )

    assert result["reference"] == "REFUSD1"
    mock_rate.assert_not_awaited()
    mock_convert.assert_not_called()

    assert service.client.initialize_transaction.await_args is not None
    init_kwargs = service.client.initialize_transaction.await_args.kwargs
    assert init_kwargs["amount_kobo"] == STARTER_MONTHLY_SUBUNITS
    assert init_kwargs["metadata"]["currency"] == "USD"
    assert init_kwargs["metadata"]["exchange_rate"] == 1.0


@pytest.mark.asyncio
async def test_charge_renewal_uses_usd_without_fx_when_subscription_currency_usd(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc-auth",
        tenant_id=uuid4(),
        tier=PricingTier.STARTER.value,
        billing_currency="USD",
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=STARTER_MONTHLY_USD)),
        _scalar_result(mock_user),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch("app.shared.core.security.decrypt_string", return_value="user@example.com"),
        patch(
            "app.shared.core.currency.ExchangeRateService.get_ngn_rate",
            new=AsyncMock(),
        ) as mock_rate,
        patch(
            "app.shared.core.currency.ExchangeRateService.convert_usd_to_ngn",
            return_value=999999,
        ) as mock_convert,
        patch.object(
            service.client,
            "charge_authorization",
            new=AsyncMock(return_value={"status": True, "data": {"status": "success"}}),
        ) as mock_charge,
    ):
        ok = await service.charge_renewal(sub)

    assert ok is True
    mock_rate.assert_not_awaited()
    mock_convert.assert_not_called()
    assert mock_charge.await_args is not None
    charge_kwargs = mock_charge.await_args.kwargs
    assert charge_kwargs["amount_kobo"] == STARTER_MONTHLY_SUBUNITS
    assert charge_kwargs["metadata"]["currency"] == "USD"


@pytest.mark.asyncio
async def test_charge_renewal_uses_injected_exchange_runtime_for_ngn(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    fx_runtime = MagicMock()
    fx_runtime.get_ngn_rate = AsyncMock(return_value=1550.0)
    fx_runtime.convert_usd_to_ngn.return_value = 155000
    service = BillingService(
        mock_db, exchange_rate_service_factory=lambda _db: fx_runtime
    )
    sub = MagicMock(
        paystack_auth_code="enc-auth",
        tenant_id=uuid4(),
        tier=PricingTier.STARTER.value,
        billing_currency="NGN",
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=STARTER_MONTHLY_USD)),
        _scalar_result(mock_user),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch("app.shared.core.security.decrypt_string", return_value="user@example.com"),
        patch.object(
            service.client,
            "charge_authorization",
            new=AsyncMock(return_value={"status": True, "data": {"status": "success"}}),
        ),
    ):
        ok = await service.charge_renewal(sub)

    assert ok is True
    fx_runtime.get_ngn_rate.assert_awaited_once()
    fx_runtime.convert_usd_to_ngn.assert_called_once()


@pytest.mark.asyncio
async def test_charge_renewal_uses_provider_next_payment_date_when_available(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    sub = MagicMock(
        paystack_auth_code="enc-auth",
        paystack_subscription_code="SUB_123",
        tenant_id=uuid4(),
        tier=PricingTier.STARTER.value,
        billing_currency="USD",
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=STARTER_MONTHLY_USD)),
        _scalar_result(mock_user),
    ]
    provider_next = "2026-05-01T00:00:00Z"

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch("app.shared.core.security.decrypt_string", return_value="user@example.com"),
        patch.object(
            service.client,
            "charge_authorization",
            new=AsyncMock(return_value={"status": True, "data": {"status": "success"}}),
        ),
        patch.object(
            service.client,
            "fetch_subscription",
            new=AsyncMock(return_value={"data": {"next_payment_date": provider_next}}),
        ) as mock_fetch,
    ):
        ok = await service.charge_renewal(sub)

    assert ok is True
    mock_fetch.assert_awaited_once_with("SUB_123")
    assert sub.next_payment_date == datetime(2026, 5, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_charge_renewal_fallback_uses_annual_cycle_when_metadata_declares_annual(
    mock_db: MagicMock,
    configured_settings: None,
) -> None:
    service = BillingService(mock_db)
    existing_next = datetime.now(timezone.utc) + timedelta(days=2)
    sub = MagicMock(
        paystack_auth_code="enc-auth",
        paystack_subscription_code=None,
        tenant_id=uuid4(),
        tier=PricingTier.STARTER.value,
        billing_currency="USD",
        next_payment_date=existing_next,
    )
    mock_user = MagicMock(email="enc-email")
    mock_db.execute.side_effect = [
        _scalar_result(MagicMock(price_usd=STARTER_MONTHLY_USD)),
        _scalar_result(mock_user),
    ]

    with (
        patch(
            "app.modules.billing.domain.billing.paystack_shared.decrypt_string",
            return_value="AUTH",
        ),
        patch("app.shared.core.security.decrypt_string", return_value="user@example.com"),
        patch.object(
            service.client,
            "charge_authorization",
            new=AsyncMock(
                return_value={
                    "status": True,
                    "data": {
                        "status": "success",
                        "metadata": {"billing_cycle": "annual"},
                    },
                }
            ),
        ),
    ):
        ok = await service.charge_renewal(sub)

    assert ok is True
    assert sub.next_payment_date is not None
    assert sub.next_payment_date >= existing_next + timedelta(days=364)
