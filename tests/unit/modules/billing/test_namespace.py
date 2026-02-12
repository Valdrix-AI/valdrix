from fastapi import APIRouter

from app.modules.billing import (
    BillingService,
    CheckoutRequest,
    PricingPlanUpdate,
    SubscriptionResponse,
    TenantSubscription,
    WebhookHandler,
    router,
)
from app.modules.billing.api.v1.billing import router as billing_api_router


def test_billing_namespace_exports_core_interfaces() -> None:
    assert isinstance(router, APIRouter)
    assert router is billing_api_router
    assert BillingService is not None
    assert TenantSubscription is not None
    assert WebhookHandler is not None
    assert CheckoutRequest is not None
    assert PricingPlanUpdate is not None
    assert SubscriptionResponse is not None

