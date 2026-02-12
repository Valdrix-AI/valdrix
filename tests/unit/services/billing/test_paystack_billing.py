import pytest
import hmac
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.modules.billing.domain.billing.paystack_billing import (
    PaystackClient, BillingService, WebhookHandler, 
    SubscriptionStatus
)
from app.shared.core.pricing import PricingTier
from fastapi import HTTPException

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock() # .add is sync
    return db

@pytest.fixture
def mock_settings():
    with patch("app.modules.billing.domain.billing.paystack_billing.settings") as m:
        m.PAYSTACK_SECRET_KEY = "sk_test_123"
        m.PAYSTACK_PLAN_STARTER = "PLN_1"
        m.PAYSTACK_PLAN_GROWTH = "PLN_2"
        m.PAYSTACK_PLAN_PRO = "PLN_3"
        m.PAYSTACK_PLAN_ENTERPRISE = "PLN_4"
        yield m

class TestPaystackClient:
    @pytest.mark.asyncio
    async def test_paystack_client_init_error(self):
        with patch("app.modules.billing.domain.billing.paystack_billing.settings") as m:
            m.PAYSTACK_SECRET_KEY = None
            with pytest.raises(ValueError, match="PAYSTACK_SECRET_KEY not configured"):
                PaystackClient()

    @pytest.mark.asyncio
    async def test_request_success(self, mock_settings):
        client = PaystackClient()
        with patch("httpx.AsyncClient.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"status": True, "data": {}}
            mock_resp.raise_for_status.return_value = None
            mock_req.return_value = mock_resp
            
            res = await client._request("POST", "test", {"foo": "bar"})
            assert res["status"] is True

    @pytest.mark.asyncio
    async def test_request_error(self, mock_settings):
        client = PaystackClient()
        from httpx import HTTPError
        with patch("httpx.AsyncClient.request", side_effect=HTTPError("conn error")):
            with pytest.raises(HTTPError):
                await client._request("GET", "test")

class TestBillingService:
    @pytest.mark.asyncio
    async def test_create_checkout_session_trial_error(self, mock_db, mock_settings):
        # Patch client initialization or handle it carefully
        with patch("app.modules.billing.domain.billing.paystack_billing.PaystackClient"):
            service = BillingService(mock_db)
            with pytest.raises(ValueError, match="Cannot checkout free_trial tier"):
                await service.create_checkout_session(uuid4(), PricingTier.FREE_TRIAL, "e@e.com", "http://url")

    @pytest.mark.asyncio
    async def test_create_checkout_session_success(self, mock_db, mock_settings):
        tenant_id = uuid4()
        with patch("app.modules.billing.domain.billing.paystack_billing.PaystackClient") as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.initialize_transaction = AsyncMock(return_value={"data": {"authorization_url": "http://pay", "reference": "ref1"}})
            
            service = BillingService(mock_db)
            
            with patch("app.modules.billing.domain.billing.currency.ExchangeRateService.get_ngn_rate", return_value=1500.0), \
                 patch("app.modules.billing.domain.billing.currency.ExchangeRateService.convert_usd_to_ngn", return_value=1500000):
                
                mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
                
                res = await service.create_checkout_session(tenant_id, PricingTier.STARTER, "e@e.com", "http://callback")
                assert res["url"] == "http://pay"
                assert res["reference"] == "ref1"

    @pytest.mark.asyncio
    async def test_charge_renewal_no_auth_code(self, mock_db, mock_settings):
        with patch("app.modules.billing.domain.billing.paystack_billing.PaystackClient"):
            service = BillingService(mock_db)
            sub = MagicMock()
            sub.paystack_auth_code = None
            res = await service.charge_renewal(sub)
            assert res is False

    @pytest.mark.asyncio
    async def test_charge_renewal_success(self, mock_db, mock_settings):
        tenant_id = uuid4()
        with patch("app.modules.billing.domain.billing.paystack_billing.PaystackClient") as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.charge_authorization = AsyncMock(return_value={"status": True, "data": {"status": "success"}})
            
            service = BillingService(mock_db)
            sub = MagicMock()
            sub.paystack_auth_code = "encrypted_auth"
            sub.tenant_id = tenant_id
            sub.tier = "starter"
            
            with patch("app.modules.billing.domain.billing.paystack_billing.decrypt_string", return_value="AUTH_123"), \
                 patch("app.modules.billing.domain.billing.currency.ExchangeRateService") as MockExchangeService, \
                 patch("app.shared.core.security.decrypt_string", return_value="user@email.com"):
                
                # Mock Exchange Service instance
                mock_exchange = MockExchangeService.return_value
                mock_exchange.get_ngn_rate = AsyncMock(return_value=1500.0)
                mock_exchange.convert_usd_to_ngn.return_value = 1500000

                # Mock PricingPlan lookup
                mock_plan_res = MagicMock()
                mock_plan_res.scalar_one_or_none.return_value = MagicMock(price_usd=10.0)
                
                 # Mock User lookup
                mock_user_res = MagicMock()
                mock_user_res.scalar_one_or_none.return_value = MagicMock(email="encrypted_email")
                
                mock_db.execute.side_effect = [mock_plan_res, mock_user_res]
                
                with patch("app.modules.billing.domain.billing.paystack_billing.logger") as mock_logger:
                    res = await service.charge_renewal(sub)
                    
                    # Add failure info if assertions fail
                    if not res:
                        print(f"DEBUG: Charge renewal failed. DB calls: {mock_db.execute.call_count}")
                        if mock_logger.error.called:
                            print(f"DEBUG: Logger errors: {mock_logger.error.call_args_list}")
                            
                    assert res is True
                assert sub.next_payment_date is not None

class TestWebhookHandler:
    @pytest.mark.asyncio
    async def test_verify_signature(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        payload = b'{"msg":"hello"}'
        signature = hmac.new(b"sk_test_123", payload, hashlib.sha512).hexdigest()
        assert handler.verify_signature(payload, signature) is True
        assert handler.verify_signature(payload, "bad") is False

    @pytest.mark.asyncio
    async def test_handle_invalid_signature(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        with pytest.raises(HTTPException) as exc:
            await handler.handle(b"{}", "bad")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_handle_charge_success_with_metadata(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        tenant_id = uuid4()
        payload = json.dumps({
            "event": "charge.success",
            "data": {
                "metadata": {"tenant_id": str(tenant_id), "tier": "pro"},
                "customer": {"customer_code": "CUS_123", "email": "e@e.com"},
                "plan": {"plan_code": "PLN_123"},
                "authorization": {"authorization_code": "AUTH_123"}
            }
        }).encode()
        
        signature = hmac.new(b"sk_test_123", payload, hashlib.sha512).hexdigest()
        
        with patch("app.modules.billing.domain.billing.paystack_billing.encrypt_string", return_value="encrypted_auth"):
            mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
            res = await handler.handle(payload, signature)
            assert res == {"status": "success"}

    @pytest.mark.asyncio
    async def test_handle_subscription_create(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        payload = json.dumps({
            "event": "subscription.create",
            "data": {
                "customer": {"customer_code": "CUS_123"},
                "subscription_code": "SUB_123",
                "email_token": "TOK_123",
                "next_payment_date": "2024-01-01T00:00:00Z"
            }
        }).encode()
        
        signature = hmac.new(b"sk_test_123", payload, hashlib.sha512).hexdigest()
        
        sub = MagicMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: sub)
        
        await handler.handle(payload, signature)
        assert sub.paystack_subscription_code == "SUB_123"
        assert sub.status == SubscriptionStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_handle_subscription_disable(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        payload = json.dumps({
            "event": "subscription.disable",
            "data": {
                "subscription_code": "SUB_123"
            }
        }).encode()
        
        signature = hmac.new(b"sk_test_123", payload, hashlib.sha512).hexdigest()
        
        sub = MagicMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: sub)
        
        await handler.handle(payload, signature)
        assert sub.status == SubscriptionStatus.CANCELLED.value
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_handle_invoice_failed(self, mock_db, mock_settings):
        handler = WebhookHandler(mock_db)
        payload = json.dumps({
            "event": "invoice.payment_failed",
            "data": {
                "subscription_code": "SUB_123",
                "invoice_code": "INV_123"
            }
        }).encode()
        
        signature = hmac.new(b"sk_test_123", payload, hashlib.sha512).hexdigest()
        
        sub = MagicMock()
        sub.id = uuid4()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: sub)
        
        with patch("app.modules.billing.domain.billing.dunning_service.DunningService.process_failed_payment", new_callable=AsyncMock) as mock_dunning:
            await handler.handle(payload, signature)
            mock_dunning.assert_called_once_with(sub.id, is_webhook=True)
