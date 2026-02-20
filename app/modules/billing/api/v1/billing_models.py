from typing import Any, Dict, Optional

from pydantic import BaseModel


class ExchangeRateUpdate(BaseModel):
    rate: float
    provider: str = "manual"


class PricingPlanUpdate(BaseModel):
    price_usd: float
    features: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None


class CheckoutRequest(BaseModel):
    tier: str  # starter, growth, pro, enterprise
    billing_cycle: str = "monthly"  # monthly, annual
    currency: Optional[str] = None  # NGN (default), USD (feature-gated)
    callback_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    next_payment_date: Optional[str] = None


class ConnectionUsageItem(BaseModel):
    connected: int
    limit: int | None
    remaining: int | None
    utilization_percent: float | None


class BillingUsageResponse(BaseModel):
    tier: str
    connections: Dict[str, ConnectionUsageItem]
    generated_at: str
