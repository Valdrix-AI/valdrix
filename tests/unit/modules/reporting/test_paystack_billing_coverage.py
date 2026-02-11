import pytest
import uuid
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.reporting.domain.billing.paystack_billing import (
    BillingService, 
    WebhookHandler,
    TenantSubscription
)
from app.shared.core.pricing import PricingTier

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def billing_service(mock_db):
    with patch("app.modules.reporting.domain.billing.paystack_billing.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "test-key"
        return BillingService(mock_db)

@pytest.mark.asyncio
async def test_charge_renewal_success(billing_service, mock_db):
    """Test successful renewal charge."""
    sub = TenantSubscription(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        tier=PricingTier.STARTER.value,
        paystack_auth_code="encrypted-auth-code"
    )
    
    with patch("app.modules.reporting.domain.billing.paystack_billing.decrypt_string", return_value="AUTH_123"), \
         patch("app.modules.reporting.domain.billing.paystack_billing.PaystackClient.charge_authorization") as mock_charge:
        
        mock_charge.return_value = {"status": True, "data": {"status": "success"}}
        
        # Mock User lookup
        mock_user = MagicMock()
        mock_user.email = "encrypted-email"
        
        mock_result_plan = MagicMock()
        mock_result_plan.scalar_one_or_none.return_value = None
        
        mock_result_rate = MagicMock()
        mock_result_rate.scalar_one_or_none.return_value = MagicMock(rate=1500.0, last_updated=datetime.now(timezone.utc))
        
        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = mock_user
        
        mock_db.execute.side_effect = [mock_result_plan, mock_result_rate, mock_result_user]
        
        with patch("app.shared.core.security.decrypt_string", return_value="test@example.com"):
            success = await billing_service.charge_renewal(sub)
            assert success is True
            assert sub.next_payment_date is not None

@pytest.mark.asyncio
async def test_webhook_handler_invalid_signature(mock_db):
    """Test webhook rejection with invalid signature."""
    from fastapi import HTTPException
    handler = WebhookHandler(mock_db)
    payload = b'{"event":"test"}'
    
    with patch("app.modules.reporting.domain.billing.paystack_billing.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "secret"
        
        with pytest.raises(HTTPException) as exc:
            await handler.handle(payload, "wrong-signature")
        assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_webhook_handle_charge_success(mock_db):
    """Test handling of charge.success webhook."""
    handler = WebhookHandler(mock_db)
    tenant_id = uuid.uuid4()
    payload = json.dumps({
        "event": "charge.success",
        "data": {
            "metadata": {"tenant_id": str(tenant_id), "tier": "starter"},
            "customer": {"customer_code": "CUS_123", "email": "test@example.com"},
            "authorization": {"authorization_code": "AUTH_123"}
        }
    }).encode()
    
    with patch.object(handler, "verify_signature", return_value=True):
        # Mock successful lookup and update
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None # No existing sub
        mock_db.execute.return_value = mock_result
        
        with patch("app.modules.reporting.domain.billing.paystack_billing.encrypt_string", return_value="encrypted-auth"):
            response = await handler.handle(payload, "valid-sig")
            assert response["status"] == "success"
            mock_db.add.assert_called() # Should add new subscription
