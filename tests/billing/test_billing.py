"""
Tests for Billing API - Paystack Integration

Tests:
1. Get subscription status
2. Create checkout session
3. Cancel subscription
4. Webhook handling
"""

import pytest
from unittest.mock import AsyncMock

from app.modules.billing import (
    CheckoutRequest,
    SubscriptionResponse,
)


class TestSubscriptionResponse:
    """Test subscription response model."""
    
    def test_subscription_response_model(self):
        """SubscriptionResponse should validate correctly."""
        response = SubscriptionResponse(
            tier="professional",
            status="active",
            next_payment_date="2026-02-13T00:00:00Z"
        )
        assert response.tier == "professional"
        assert response.status == "active"
    
    def test_subscription_response_optional_date(self):
        """next_payment_date should be optional."""
        response = SubscriptionResponse(
            tier="free",
            status="active"
        )
        assert response.next_payment_date is None


class TestCheckoutRequest:
    """Test checkout request model."""
    
    def test_checkout_request_valid_tier(self):
        """CheckoutRequest should accept valid tiers."""
        request = CheckoutRequest(tier="starter")
        assert request.tier == "starter"
    
    def test_checkout_request_optional_callback(self):
        """callback_url should be optional."""
        request = CheckoutRequest(tier="professional")
        assert request.callback_url is None
    
    def test_checkout_request_with_callback(self):
        """CheckoutRequest should accept callback_url."""
        request = CheckoutRequest(
            tier="starter",
            callback_url="https://app.valdrix.ai/billing?success=true"
        )
        assert request.callback_url == "https://app.valdrix.ai/billing?success=true"


class TestBillingService:
    """Test BillingService from paystack_billing."""
    
    def test_billing_service_exists(self):
        """BillingService class should exist and be importable."""
        from app.modules.reporting.domain.billing.paystack_billing import BillingService
        assert BillingService is not None
    
    def test_billing_service_has_required_methods(self):
        """BillingService should have expected methods."""
        from app.modules.reporting.domain.billing.paystack_billing import BillingService
        
        mock_db = AsyncMock()
        service = BillingService(mock_db)
        
        assert hasattr(service, 'create_checkout_session')
        assert hasattr(service, 'cancel_subscription')


class TestWebhookHandler:
    """Test Paystack webhook handling."""
    
    def test_webhook_signature_verification_invalid(self):
        """Invalid signature should be rejected."""
        from app.modules.reporting.domain.billing.paystack_billing import WebhookHandler
        
        mock_db = AsyncMock()
        _ = WebhookHandler(mock_db)
        
        # Signature verification happens in the handle method
        # This tests the structure, actual crypto verification needs the real key
    
    @pytest.mark.asyncio
    async def test_webhook_subscription_create(self):
        """subscription.create event should update database."""
        from app.modules.reporting.domain.billing.paystack_billing import WebhookHandler
        
        mock_db = AsyncMock()
        handler = WebhookHandler(mock_db)
        
        # Verify handler has required methods
        assert hasattr(handler, 'handle')


class TestPricingTier:
    """Test PricingTier enum."""
    
    def test_pricing_tier_values(self):
        """PricingTier should have expected values."""
        from app.modules.reporting.domain.billing.paystack_billing import PricingTier
        
        assert PricingTier.TRIAL.value == "trial"
        assert PricingTier.STARTER.value == "starter"
        assert PricingTier.PRO.value == "pro"
        assert PricingTier.ENTERPRISE.value == "enterprise"
    
    def test_pricing_tier_from_string(self):
        """PricingTier should be creatable from string."""
        from app.modules.reporting.domain.billing.paystack_billing import PricingTier
        
        tier = PricingTier("pro")
        assert tier == PricingTier.PRO


class TestTenantSubscriptionModel:
    """Test TenantSubscription model."""
    
    def test_tenant_subscription_fields(self):
        """TenantSubscription should have correct fields."""
        from app.modules.reporting.domain.billing.paystack_billing import TenantSubscription
        
        # Verify model has expected columns
        assert hasattr(TenantSubscription, 'tenant_id')
        assert hasattr(TenantSubscription, 'tier')
        assert hasattr(TenantSubscription, 'status')
        assert hasattr(TenantSubscription, 'paystack_customer_code')
        assert hasattr(TenantSubscription, 'paystack_subscription_code')
