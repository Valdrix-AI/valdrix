"""
Billing API Endpoints - Paystack Integration

Provides:
- GET /billing/subscription - Current subscription status
- POST /billing/checkout - Initialize Paystack checkout
- POST /billing/webhook - Handle Paystack webhooks
"""

import ipaddress
from typing import Annotated, Optional, Dict, Any, List
from urllib.parse import urlparse, urljoin, urlunparse
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.modules.billing.api.v1.billing_models import (
    BillingUsageResponse,
    CheckoutRequest,
    ExchangeRateUpdate,
    PricingPlanUpdate,
    SubscriptionResponse,
)
from app.modules.billing.api.v1.billing_ops import (
    apply_exchange_rate_update,
    apply_pricing_plan_update,
    load_billing_usage,
    load_exchange_rate_health,
    load_public_plans,
    process_paystack_webhook,
)
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.db.session import get_db
from app.shared.core.config import get_settings
from app.shared.core.rate_limit import auth_limit, standard_limit
from app.shared.core.currency import ExchangeRateUnavailableError

logger = structlog.get_logger()
router = APIRouter(tags=["Billing"])


class _SettingsProxy:
    """Lazy settings accessor to avoid stale module-level configuration."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)


settings: Any = _SettingsProxy()


def _build_checkout_callback_url(raw_callback_url: Optional[str]) -> str:
    """
    Validate and normalize user-provided checkout callback URLs.

    Security controls:
    - only allow same-site callback hosts (frontend + configured CORS origins)
    - enforce HTTPS in staging/production
    - block credentialed URLs
    """
    default_callback = f"{settings.FRONTEND_URL.rstrip('/')}/billing?success=true"
    candidate = (raw_callback_url or "").strip()
    callback = candidate or default_callback

    # Treat relative callback paths as frontend-local redirects.
    if callback.startswith("/"):
        callback = urljoin(
            settings.FRONTEND_URL.rstrip("/") + "/", callback.lstrip("/")
        )

    parsed = urlparse(callback)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "Invalid callback_url")
    if parsed.username or parsed.password:
        raise HTTPException(400, "callback_url must not include credentials")

    if settings.ENVIRONMENT in {"production", "staging"} and parsed.scheme != "https":
        raise HTTPException(
            400, "callback_url must use HTTPS in production environments"
        )

    allowed_hosts: set[str] = set()
    if settings.FRONTEND_URL:
        frontend_host = (urlparse(settings.FRONTEND_URL).hostname or "").lower()
        if frontend_host:
            allowed_hosts.add(frontend_host)
    for origin in settings.CORS_ORIGINS:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host:
            allowed_hosts.add(origin_host)

    callback_host = (parsed.hostname or "").lower()
    if callback_host not in allowed_hosts:
        raise HTTPException(400, "callback_url host is not allowed")

    # Strip fragment to avoid client-side script injection vectors through URL anchors.
    sanitized = parsed._replace(fragment="")
    return urlunparse(sanitized)


def _extract_client_ip(request: Request) -> str:
    """
    Resolve request source IP with defensive XFF parsing.

    We prefer the right-most valid XFF entry (closest upstream hop) and
    fall back to `request.client.host`.
    """
    fallback = request.client.host if request.client and request.client.host else "unknown"
    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return fallback

    candidates = [part.strip() for part in xff.split(",") if part.strip()]
    for raw in reversed(candidates):
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            continue
    return fallback


@router.get("/plans")
@standard_limit
async def get_public_plans(
    request: Request, db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get public pricing plans for the landing page.
    No authentication required.
    Tries DB first, fallbacks to TIER_CONFIG.
    """
    return await load_public_plans(db, logger=logger)


@router.get("/subscription", response_model=SubscriptionResponse)
@auth_limit
async def get_subscription(
    request: Request,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Get current subscription status for tenant."""
    try:
        from app.modules.billing.domain.billing.paystack_billing import (
            TenantSubscription,
        )

        result = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == user.tenant_id
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            return SubscriptionResponse(tier="free", status="active")

        return SubscriptionResponse(
            tier=sub.tier,
            status=sub.status,
            next_payment_date=sub.next_payment_date.isoformat()
            if sub.next_payment_date
            else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_subscription_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch subscription") from e


@router.get("/features")
@auth_limit
async def get_features(
    request: Request,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
) -> Dict[str, Any]:
    """
    Get enabled features and limits for the user's current tier.
    Central authority for frontend and backend gating.
    """
    from app.shared.core.pricing import PricingTier, get_tier_config

    user_tier = getattr(user, "tier", PricingTier.FREE)
    config = get_tier_config(user_tier)

    return {
        "tier": user_tier,
        "features": list(config.get("features", [])),
        "limits": config.get("limits", {}),
    }


@router.get("/usage", response_model=BillingUsageResponse)
@auth_limit
async def get_billing_usage(
    request: Request,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
) -> BillingUsageResponse:
    """
    Tier-aligned usage overview for billing/packaging UX.

    This surfaces how close a tenant is to connection limits (AWS/Azure/GCP/SaaS/License),
    so upgrades are explainable and enforceable.
    """
    from app.shared.core.pricing import PricingTier

    tier = getattr(user, "tier", PricingTier.FREE)
    connections = await load_billing_usage(
        db,
        tenant_id=user.tenant_id,
        tier=tier,
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return BillingUsageResponse(
        tier=tier.value if hasattr(tier, "value") else str(tier),
        connections=connections,
        generated_at=now.isoformat(),
    )


@router.post("/checkout")
@auth_limit
async def create_checkout(
    request: Request,
    checkout_req: CheckoutRequest,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Initialize Paystack checkout session."""
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(503, "Billing not configured")

    try:
        from app.modules.billing.domain.billing.paystack_billing import BillingService
        from app.shared.core.pricing import PricingTier

        # Validate tier
        try:
            tier = PricingTier(checkout_req.tier.lower())
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {checkout_req.tier}")

        billing = BillingService(db)

        callback = _build_checkout_callback_url(checkout_req.callback_url)

        if not user.tenant_id:
            raise HTTPException(400, "User has no tenant")

        result = await billing.create_checkout_session(
            tenant_id=user.tenant_id,
            tier=tier,
            email=user.email,
            callback_url=callback,
            billing_cycle=checkout_req.billing_cycle,
            currency=checkout_req.currency,
        )

        return {"checkout_url": result["url"], "reference": result["reference"]}

    except ExchangeRateUnavailableError as e:
        logger.warning("checkout_rate_unavailable", error=str(e))
        raise HTTPException(
            503, "Live FX rate unavailable. Please try checkout again shortly."
        ) from e
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("checkout_failed", error=str(e))
        raise HTTPException(500, "Failed to create checkout session") from e


@router.post("/cancel")
async def cancel_subscription(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Cancel current subscription."""
    try:
        from app.modules.billing.domain.billing.paystack_billing import BillingService

        billing = BillingService(db)
        if not user.tenant_id:
            raise HTTPException(400, "User has no tenant")
        await billing.cancel_subscription(user.tenant_id)

        return {"status": "cancelled"}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("cancel_failed", error=str(e))
        raise HTTPException(500, "Failed to cancel subscription") from e


@router.post("/webhook")
async def handle_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Handle Paystack webhook events with durable processing.

    Webhooks are stored in background_jobs before processing,
    enabling automatic retry on failure.
    """
    try:
        return await process_paystack_webhook(
            request,
            db,
            settings=settings,
            logger=logger,
            extract_client_ip=_extract_client_ip,
        )
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
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually update exchange rate."""
    return await apply_exchange_rate_update(
        db,
        rate=request.rate,
        provider=request.provider,
    )


@router.get("/admin/rates")
async def get_exchange_rate(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get current exchange rate with billing safety health flags."""
    return await load_exchange_rate_health(db, logger=logger)


@router.post("/admin/plans/{plan_id}")
@auth_limit
async def update_pricing_plan(
    request: Request,
    plan_id: str,  # Note: plan_id is a slug (e.g., 'starter'), not a UUID
    plan_req: PricingPlanUpdate,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Update pricing plan details."""
    return await apply_pricing_plan_update(
        db,
        plan_id=plan_id,
        price_usd=plan_req.price_usd,
        features=plan_req.features,
        limits=plan_req.limits,
    )
