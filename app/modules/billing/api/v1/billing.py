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
from sqlalchemy import select, func, union_all, literal
from pydantic import BaseModel
import structlog

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
    from app.models.pricing import PricingPlan
    from app.shared.core.pricing import TIER_CONFIG, PricingTier

    # 1. Try fetching from DB
    try:
        result = await db.execute(
            select(
                PricingPlan.id,
                PricingPlan.name,
                PricingPlan.price_usd,
                PricingPlan.description,
                PricingPlan.display_features,
                PricingPlan.cta_text,
                PricingPlan.is_popular,
            ).where(PricingPlan.is_active.is_(True))
        )
        db_plans = result.mappings().all()
        if db_plans:
            return [
                {
                    "id": str(p["id"]),
                    "name": p["name"],
                    "price_monthly": float(p["price_usd"]),
                    "price_annual": float(p["price_usd"])
                    * 10,  # Standard 2-months-free fallback
                    "period": "/mo",
                    "description": p["description"],
                    "features": p["display_features"],
                    "cta": p["cta_text"],
                    "popular": bool(p["is_popular"]),
                }
                for p in db_plans
            ]
    except Exception as e:
        logger.warning("failed_to_fetch_plans_from_db", error=str(e))

    # 2. Fallback to hardcoded TIER_CONFIG
    public_plans = []
    for tier in [PricingTier.STARTER, PricingTier.GROWTH, PricingTier.PRO]:
        config = TIER_CONFIG.get(tier)
        if config:
            price_cfg = config["price_usd"]
            if not isinstance(price_cfg, dict):
                logger.error(
                    "invalid_tier_price_config",
                    tier=tier.value,
                    expected_type="dict",
                    actual_type=type(price_cfg).__name__,
                )
                continue
            monthly = price_cfg["monthly"]
            annual = price_cfg["annual"]

            public_plans.append(
                {
                    "id": tier.value,
                    "name": config.get("name", tier.value.capitalize()),
                    "price_monthly": monthly,
                    "price_annual": annual,
                    "period": "/mo",
                    "description": config.get("description", ""),
                    "features": config.get("display_features", []),
                    "cta": config.get("cta", "Get Started"),
                    "popular": tier == PricingTier.GROWTH,
                }
            )

    return public_plans


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
    from datetime import datetime, timezone
    from app.models.aws_connection import AWSConnection
    from app.models.azure_connection import AzureConnection
    from app.models.gcp_connection import GCPConnection
    from app.models.saas_connection import SaaSConnection
    from app.models.license_connection import LicenseConnection
    from app.shared.core.pricing import PricingTier, get_tier_limit

    tier = getattr(user, "tier", PricingTier.FREE)

    def _usage_item(connected: int, limit_value: Any) -> ConnectionUsageItem:
        if limit_value is None:
            return ConnectionUsageItem(
                connected=connected,
                limit=None,
                remaining=None,
                utilization_percent=None,
            )
        try:
            limit_int = int(limit_value)
        except (TypeError, ValueError):
            limit_int = 0
        if limit_int <= 0:
            return ConnectionUsageItem(
                connected=connected,
                limit=limit_int,
                remaining=0,
                utilization_percent=None,
            )
        remaining = max(limit_int - connected, 0)
        utilization = round((connected / limit_int) * 100, 1) if limit_int > 0 else None
        return ConnectionUsageItem(
            connected=connected,
            limit=limit_int,
            remaining=remaining,
            utilization_percent=utilization,
        )

    count_rows = union_all(
        select(
            literal("aws").label("provider"),
            func.count().label("connected"),
        )
        .select_from(AWSConnection)
        .where(AWSConnection.tenant_id == user.tenant_id),
        select(
            literal("azure").label("provider"),
            func.count().label("connected"),
        )
        .select_from(AzureConnection)
        .where(AzureConnection.tenant_id == user.tenant_id),
        select(
            literal("gcp").label("provider"),
            func.count().label("connected"),
        )
        .select_from(GCPConnection)
        .where(GCPConnection.tenant_id == user.tenant_id),
        select(
            literal("saas").label("provider"),
            func.count().label("connected"),
        )
        .select_from(SaaSConnection)
        .where(SaaSConnection.tenant_id == user.tenant_id),
        select(
            literal("license").label("provider"),
            func.count().label("connected"),
        )
        .select_from(LicenseConnection)
        .where(LicenseConnection.tenant_id == user.tenant_id),
    )
    counts_subquery = count_rows.subquery()
    counts_result = await db.execute(
        select(counts_subquery.c.provider, counts_subquery.c.connected)
    )
    counts_map = {
        str(row.provider): int(row.connected or 0) for row in counts_result.all()
    }
    aws_count = counts_map.get("aws", 0)
    azure_count = counts_map.get("azure", 0)
    gcp_count = counts_map.get("gcp", 0)
    saas_count = counts_map.get("saas", 0)
    license_count = counts_map.get("license", 0)

    connections: Dict[str, ConnectionUsageItem] = {
        "aws": _usage_item(aws_count, get_tier_limit(tier, "max_aws_accounts")),
        "azure": _usage_item(azure_count, get_tier_limit(tier, "max_azure_tenants")),
        "gcp": _usage_item(gcp_count, get_tier_limit(tier, "max_gcp_projects")),
        "saas": _usage_item(saas_count, get_tier_limit(tier, "max_saas_connections")),
        "license": _usage_item(
            license_count, get_tier_limit(tier, "max_license_connections")
        ),
    }

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
        from app.modules.billing.domain.billing.paystack_billing import WebhookHandler
        from app.modules.billing.domain.billing.webhook_retry import WebhookRetryService
        import json

        # BE-BILLING-1: Validate Paystack origin IP (Mandatory for SOC2/Security)
        PAYSTACK_IPS = {"52.31.139.75", "52.49.173.169", "52.214.14.220"}
        client_ip = _extract_client_ip(request)

        if (
            settings.ENVIRONMENT in {"production", "staging"}
            and client_ip not in PAYSTACK_IPS
        ):
            logger.warning("unauthorized_webhook_origin", ip=client_ip)
            raise HTTPException(403, "Unauthorized origin IP")

        # Finding #12: Reject non-JSON payloads to prevent request forgery
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise HTTPException(
                415, "Unsupported Media Type: expected application/json"
            )

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
        try:
            raw_payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning("webhook_payload_not_utf8")
            raise HTTPException(400, "Invalid webhook payload encoding") from exc

        job = await retry_service.store_webhook(
            provider="paystack",
            event_type=event_type,
            payload=data,
            reference=reference,
            signature=signature,
            raw_payload=raw_payload,
        )

        if job is None:
            # Duplicate webhook (already queued or already processed).
            return {"status": "duplicate", "message": "Already queued or processed"}

        # Process immediately (job stored for retry if fails)
        try:
            result = await handler.handle(request, payload, signature)
            return result
        except Exception as process_error:
            logger.warning(
                "webhook_processing_failed_will_retry",
                job_id=str(job.id),
                error=str(process_error),
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
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually update exchange rate."""
    from app.models.pricing import ExchangeRate
    from datetime import datetime, timezone

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.from_currency == "USD", ExchangeRate.to_currency == "NGN"
        )
    )
    rate_obj = result.scalar_one_or_none()

    if rate_obj:
        rate_obj.rate = request.rate
        rate_obj.provider = request.provider
        rate_obj.last_updated = datetime.now(timezone.utc)
    else:
        db.add(
            ExchangeRate(
                from_currency="USD",
                to_currency="NGN",
                rate=request.rate,
                provider=request.provider,
            )
        )

    await db.commit()
    return {"status": "success", "rate": request.rate}


@router.get("/admin/rates")
async def get_exchange_rate(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get current exchange rate with billing safety health flags."""
    from app.models.pricing import ExchangeRate
    from datetime import datetime, timezone

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.from_currency == "USD", ExchangeRate.to_currency == "NGN"
        )
    )
    rate_obj = result.scalar_one_or_none()

    if not rate_obj:
        return {
            "rate": None,
            "provider": "unavailable",
            "last_updated": None,
            "age_hours": None,
            "is_stale": None,
            "is_official_provider": None,
            "billing_safe": False,
            "warning": "No USD->NGN rate row available in cache",
        }

    now_utc = datetime.now(timezone.utc)
    updated_at = rate_obj.last_updated
    if updated_at and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_hours = None
    is_stale = None
    if updated_at:
        age_hours = round(
            (now_utc - updated_at).total_seconds() / 3600,
            2,
        )
        is_stale = age_hours > 24
    provider = str(rate_obj.provider or "").strip().lower()
    is_official_provider = provider == "cbn_nfem"
    billing_safe = bool(is_official_provider and is_stale is False)
    warning = None
    if not is_official_provider:
        warning = (
            "Provider is not official CBN NFEM; strict billing will reject this rate."
        )
    elif is_stale:
        warning = "CBN rate is older than 24h; strict billing will reject checkout."
    if warning:
        logger.warning(
            "billing_fx_guardrail_triggered",
            provider=provider or "unknown",
            age_hours=age_hours,
            is_stale=is_stale,
            billing_safe=billing_safe,
        )

    return {
        "rate": float(rate_obj.rate),
        "provider": rate_obj.provider,
        "last_updated": updated_at.isoformat() if updated_at else None,
        "age_hours": age_hours,
        "is_stale": is_stale,
        "is_official_provider": is_official_provider,
        "billing_safe": billing_safe,
        "warning": warning,
    }


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
    from app.models.pricing import PricingPlan

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
