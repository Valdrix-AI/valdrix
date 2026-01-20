"""
Billing API Endpoints - Paystack Integration

Provides:
- GET /billing/subscription - Current subscription status
- POST /billing/checkout - Initialize Paystack checkout
- POST /billing/webhook - Handle Paystack webhooks
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.core.auth import CurrentUser, requires_role
from app.db.session import get_db
from app.core.config import get_settings
from app.core.rate_limit import auth_limit

logger = structlog.get_logger()
router = APIRouter(tags=["Billing"])
settings = get_settings()

class ExchangeRateUpdate(BaseModel):
    rate: float
    provider: str = "manual"

class PricingPlanUpdate(BaseModel):
    price_usd: float
    features: Optional[dict] = None
    limits: Optional[dict] = None


class CheckoutRequest(BaseModel):
    tier: str  # starter, growth, pro, enterprise
    billing_cycle: str = "monthly"  # monthly, annual
    callback_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    next_payment_date: Optional[str] = None


@router.get("/plans")
async def get_public_plans(db: AsyncSession = Depends(get_db)):
    """
    Get public pricing plans for the landing page.
    No authentication required.
    Tries DB first, fallbacks to TIER_CONFIG.
    """
    from app.models.pricing import PricingPlan
    from sqlalchemy import select
    from app.core.pricing import TIER_CONFIG, PricingTier
    
    # 1. Try fetching from DB
    try:
        result = await db.execute(select(PricingPlan).where(PricingPlan.is_active == True))
        db_plans = result.scalars().all()
        if db_plans:
            return [{
                "id": p.id,
                "name": p.name,
                "price": float(p.price_usd),
                "period": "/mo",
                "description": p.description,
                "features": p.display_features,
                "cta": p.cta_text,
                "popular": p.is_popular
            } for p in db_plans]
    except Exception as e:
        logger.warning("failed_to_fetch_plans_from_db", error=str(e))

    # 2. Fallback to hardcoded TIER_CONFIG
    public_plans = []
    for tier in [PricingTier.STARTER, PricingTier.GROWTH, PricingTier.PRO]:
        config = TIER_CONFIG.get(tier)
        if config:
            price_cfg = config["price_usd"]
            # Handle both legacy int and new dict formats
            monthly = price_cfg["monthly"] if isinstance(price_cfg, dict) else price_cfg
            annual = price_cfg["annual"] if isinstance(price_cfg, dict) else (price_cfg * 10) # Fallback 2 months free
            
            public_plans.append({
                "id": tier.value,
                "name": config["name"],
                "price_monthly": monthly,
                "price_annual": annual,
                "period": "/mo",
                "description": config["description"],
                "features": config["display_features"],
                "cta": config["cta"],
                "popular": tier == PricingTier.GROWTH
            })
            
    return public_plans


@router.get("/subscription", response_model=SubscriptionResponse)
@auth_limit
async def get_subscription(
    request: Request,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """Get current subscription status for tenant."""
    try:
        from app.services.billing.paystack_billing import TenantSubscription
        from sqlalchemy import select

        result = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == user.tenant_id
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            return SubscriptionResponse(tier="trial", status="active")

        return SubscriptionResponse(
            tier=sub.tier,
            status=sub.status,
            next_payment_date=sub.next_payment_date.isoformat() if sub.next_payment_date else None
        )
    except Exception as e:
        logger.error("get_subscription_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch subscription") from e


@router.get("/features")
@auth_limit
async def get_features(
    request: Request,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
):
    """
    Get enabled features and limits for the user's current tier.
    Central authority for frontend and backend gating.
    """
    from app.core.pricing import PricingTier, get_tier_config
    
    user_tier = getattr(user, "tier", PricingTier.STARTER)
    config = get_tier_config(user_tier)
    
    return {
        "tier": user_tier,
        "features": list(config.get("features", [])),
        "limits": config.get("limits", {})
    }



@router.post("/checkout")
@auth_limit
async def create_checkout(
    request: Request,
    checkout_req: CheckoutRequest,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """Initialize Paystack checkout session."""
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(503, "Billing not configured")

    try:
        from app.services.billing.paystack_billing import BillingService
        from app.core.pricing import PricingTier

        # Validate tier
        try:
            tier = PricingTier(request.tier.lower())
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {request.tier}")

        billing = BillingService(db)
        
        # Default callback URL
        callback = request.callback_url or f"{settings.FRONTEND_URL}/billing?success=true"
        
        result = await billing.create_checkout_session(
            tenant_id=user.tenant_id,
            tier=tier,
            email=user.email,
            callback_url=callback,
            billing_cycle=request.billing_cycle
        )

        return {"checkout_url": result["url"], "reference": result["reference"]}

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("checkout_failed", error=str(e))
        raise HTTPException(500, "Failed to create checkout session") from e


@router.post("/cancel")
async def cancel_subscription(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """Cancel current subscription."""
    try:
        from app.services.billing.paystack_billing import BillingService

        billing = BillingService(db)
        await billing.cancel_subscription(user.tenant_id)

        return {"status": "cancelled"}

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("cancel_failed", error=str(e))
        raise HTTPException(500, "Failed to cancel subscription") from e


@router.post("/webhook")
async def handle_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Paystack webhook events with durable processing.
    
    Webhooks are stored in background_jobs before processing,
    enabling automatic retry on failure.
    """
    try:
        from app.services.billing.paystack_billing import WebhookHandler
        from app.services.billing.webhook_retry import WebhookRetryService
        import json

        # BE-BILLING-1: Validate Paystack origin IP (Mandatory for SOC2/Security)
        PAYSTACK_IPS = {"52.31.139.75", "52.49.173.169", "52.214.14.220"}
        # Check X-Forwarded-For (if behind proxy) or client host
        client_ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
        
        if settings.ENVIRONMENT == "production" and client_ip not in PAYSTACK_IPS:
            logger.warning("unauthorized_webhook_origin", ip=client_ip)
            raise HTTPException(403, "Unauthorized origin IP")

        payload = await request.body()
        signature = request.headers.get("x-paystack-signature", "")

        if not signature:
            raise HTTPException(401, "Missing signature")

        # Verify signature first
        handler = WebhookHandler(db)
        if not handler.verify_signature(payload, signature):
            raise HTTPException(401, "Invalid signature")

        # Parse payload
        data = json.loads(payload)
        event_type = data.get("event", "unknown")
        reference = data.get("data", {}).get("reference", "")

        # Store webhook for durable processing
        retry_service = WebhookRetryService(db)
        job = await retry_service.store_webhook(
            provider="paystack",
            event_type=event_type,
            payload=data,
            reference=reference
        )

        if job is None:
            # Duplicate webhook, already processed
            return {"status": "duplicate", "message": "Already processed"}

        # Process immediately (job stored for retry if fails)
        try:
            result = await handler.handle(payload, signature)
            return result
        except Exception as process_error:
            logger.warning(
                "webhook_processing_failed_will_retry",
                job_id=str(job.id),
                error=str(process_error)
            )
            # Job is already stored, will be retried by JobProcessor
            return {"status": "queued", "job_id": str(job.id)}

    except ValueError as e:
        logger.error("webhook_invalid", error=str(e))
        raise HTTPException(401, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("webhook_failed", error=str(e))
        raise HTTPException(500, "Webhook processing failed") from e

# ==================== Admin Endpoints ====================

@router.post("/admin/rates")
async def update_exchange_rate(
    request: ExchangeRateUpdate,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
):
    """Manually update exchange rate."""
    from app.models.pricing import ExchangeRate
    from sqlalchemy import select
    from datetime import datetime, timezone

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.from_currency == "USD",
            ExchangeRate.to_currency == "NGN"
        )
    )
    rate_obj = result.scalar_one_or_none()

    if rate_obj:
        rate_obj.rate = request.rate
        rate_obj.provider = request.provider
        rate_obj.last_updated = datetime.now(timezone.utc)
    else:
        db.add(ExchangeRate(
            from_currency="USD",
            to_currency="NGN",
            rate=request.rate,
            provider=request.provider
        ))
    
    await db.commit()
    return {"status": "success", "rate": request.rate}

@router.get("/admin/rates")
async def get_exchange_rate(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
):
    """Get current exchange rate."""
    from app.models.pricing import ExchangeRate
    from sqlalchemy import select

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.from_currency == "USD",
            ExchangeRate.to_currency == "NGN"
        )
    )
    rate_obj = result.scalar_one_or_none()
    
    if not rate_obj:
        return {"rate": 1450.0, "provider": "fallback"}
        
    return {
        "rate": float(rate_obj.rate),
        "provider": rate_obj.provider,
        "last_updated": rate_obj.last_updated.isoformat()
    }

@router.post("/admin/plans/{plan_id}")
@auth_limit
async def update_pricing_plan(
    request: Request,
    plan_id: str, # Note: plan_id is a slug (e.g., 'starter'), not a UUID
    plan_req: PricingPlanUpdate,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
):
    """Update pricing plan details."""
    from app.models.pricing import PricingPlan
    from sqlalchemy import select

    result = await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(404, "Plan not found")

    plan.price_usd = plan_req.price_usd
    if plan_req.features:
        plan.features = plan_req.features
    if plan_req.limits:
        plan.limits = plan_req.limits
    
    await db.commit()
    return {"status": "success", "plan_id": plan_id}
