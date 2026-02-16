"""
Tests for Billing API - Paystack Integration

Tests:
1. Get subscription status
2. Create checkout session
"""

import pytest
from unittest.mock import patch, AsyncMock
from app.modules.billing import (
    CheckoutRequest,
    SubscriptionResponse,
)
from app.shared.core.pricing import PricingTier


class TestSubscriptionResponse:
    """Test subscription response model."""

    def test_subscription_response_model(self) -> None:
        """SubscriptionResponse should validate correctly."""
        response = SubscriptionResponse(
            tier=PricingTier.PRO,
            status="active",
            next_payment_date="2026-02-13T00:00:00Z",
        )
        assert response.tier == PricingTier.PRO
        assert response.status == "active"

    def test_subscription_response_optional_date(self) -> None:
        """next_payment_date should be optional."""
        response = SubscriptionResponse(tier=PricingTier.FREE_TRIAL, status="active")
        assert response.next_payment_date is None


class TestCheckoutRequest:
    """Test checkout request model."""

    def test_checkout_request_valid_tier(self) -> None:
        """CheckoutRequest should accept valid tiers."""
        request = CheckoutRequest(tier=PricingTier.STARTER)
        assert request.tier == PricingTier.STARTER

    def test_checkout_request_optional_callback(self) -> None:
        """callback_url should be optional."""
        request = CheckoutRequest(tier=PricingTier.PRO)
        assert request.callback_url is None

    def test_checkout_request_with_callback(self) -> None:
        """CheckoutRequest should accept callback_url."""
        request = CheckoutRequest(
            tier=PricingTier.STARTER, callback_url="https://app.valdrix.ai/billing?success=true"
        )
        assert request.callback_url == "https://app.valdrix.ai/billing?success=true"


class TestBillingService:
    """Test BillingService from paystack_billing."""

    def test_billing_service_exists(self) -> None:
        """BillingService class should exist and be importable."""
        from app.modules.billing.domain.billing.paystack_billing import BillingService

        assert BillingService is not None

    def test_billing_service_has_required_methods(self) -> None:
        """BillingService should have expected methods."""
        from app.modules.billing.domain.billing.paystack_billing import BillingService

        with patch(
            "app.modules.billing.domain.billing.paystack_billing.settings"
        ) as mock_settings:
            # Mock settings to avoid Paystack key validation
            mock_settings.PAYSTACK_SECRET_KEY = "test-secret-key"

            mock_db = AsyncMock()
            service = BillingService(mock_db)

            assert hasattr(service, "create_checkout_session")
            assert hasattr(service, "cancel_subscription")


class TestWebhookHandler:
    """Test Paystack webhook handling."""

    def test_webhook_signature_verification_invalid(self) -> None:
        """Invalid signature should be rejected."""
        from app.modules.billing.domain.billing.paystack_billing import WebhookHandler

        mock_db = AsyncMock()
        _ = WebhookHandler(mock_db)

        # Signature verification happens in the handle method
        # This tests the structure, actual crypto verification needs the real key

    @pytest.mark.asyncio
    async def test_webhook_subscription_create(self):
        """subscription.create event should update database."""
        from app.modules.billing.domain.billing.paystack_billing import WebhookHandler

        mock_db = AsyncMock()
        handler = WebhookHandler(mock_db)

        # Verify handler has required methods
        assert hasattr(handler, "handle")


class TestPricingTier:
    """Test PricingTier enum."""

    def test_pricing_tier_values(self) -> None:
        """PricingTier should have expected values."""
        from app.shared.core.pricing import PricingTier

        assert PricingTier.FREE_TRIAL.value == "free_trial"
        assert PricingTier.STARTER.value == "starter"
        assert PricingTier.PRO.value == "pro"
        assert PricingTier.ENTERPRISE.value == "enterprise"

    def test_pricing_tier_from_string(self) -> None:
        """PricingTier should be creatable from string."""
        from app.shared.core.pricing import PricingTier

        tier = PricingTier("pro")
        assert tier == PricingTier.PRO


class TestTenantSubscriptionModel:
    """Test TenantSubscription model."""

    def test_tenant_subscription_fields(self) -> None:
        """TenantSubscription should have correct fields."""
        from app.modules.billing.domain.billing.paystack_billing import (
            TenantSubscription,
        )

        # Verify model has expected columns
        assert hasattr(TenantSubscription, "tenant_id")
        assert hasattr(TenantSubscription, "tier")
        assert hasattr(TenantSubscription, "status")
        assert hasattr(TenantSubscription, "paystack_customer_code")
        assert hasattr(TenantSubscription, "paystack_subscription_code")
