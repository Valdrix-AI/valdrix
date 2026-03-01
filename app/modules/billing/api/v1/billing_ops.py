from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict

from fastapi import HTTPException, Request
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.api.v1.billing_models import ConnectionUsageItem


async def load_public_plans(
    db: AsyncSession,
    *,
    logger: Any,
) -> list[dict[str, Any]]:
    from app.models.pricing import PricingPlan
    from app.shared.core.pricing import (
        PricingTier,
        TIER_CONFIG,
        get_tier_feature_maturity,
        normalize_tier,
    )

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
                    "price_annual": float(p["price_usd"]) * 10,
                    "period": "/mo",
                    "description": p["description"],
                    "features": p["display_features"],
                    "feature_maturity": (
                        get_tier_feature_maturity(normalize_tier(str(p["id"])))
                        if str(p["id"]).strip().lower()
                        in {tier.value for tier in PricingTier}
                        else {}
                    ),
                    "cta": p["cta_text"],
                    "popular": bool(p["is_popular"]),
                }
                for p in db_plans
            ]
    except Exception as exc:
        logger.warning("failed_to_fetch_plans_from_db", error=str(exc))

    public_plans: list[dict[str, Any]] = []
    for tier in [PricingTier.STARTER, PricingTier.GROWTH, PricingTier.PRO]:
        config = TIER_CONFIG.get(tier)
        if not config:
            continue
        price_cfg = config["price_usd"]
        if not isinstance(price_cfg, dict):
            logger.error(
                "invalid_tier_price_config",
                tier=tier.value,
                expected_type="dict",
                actual_type=type(price_cfg).__name__,
            )
            continue

        public_plans.append(
            {
                "id": tier.value,
                "name": config.get("name", tier.value.capitalize()),
                "price_monthly": price_cfg["monthly"],
                "price_annual": price_cfg["annual"],
                "period": "/mo",
                "description": config.get("description", ""),
                "features": config.get("display_features", []),
                "feature_maturity": get_tier_feature_maturity(tier),
                "cta": config.get("cta", "Get Started"),
                "popular": tier == PricingTier.GROWTH,
            }
        )

    return public_plans


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


async def load_billing_usage(
    db: AsyncSession,
    *,
    tenant_id: Any,
    tier: Any,
) -> dict[str, ConnectionUsageItem]:
    from app.models.aws_connection import AWSConnection
    from app.models.azure_connection import AzureConnection
    from app.models.gcp_connection import GCPConnection
    from app.models.license_connection import LicenseConnection
    from app.models.saas_connection import SaaSConnection
    from app.shared.core.pricing import get_tier_limit

    count_rows = union_all(
        select(
            literal("aws").label("provider"),
            func.count().label("connected"),
        )
        .select_from(AWSConnection)
        .where(AWSConnection.tenant_id == tenant_id),
        select(
            literal("azure").label("provider"),
            func.count().label("connected"),
        )
        .select_from(AzureConnection)
        .where(AzureConnection.tenant_id == tenant_id),
        select(
            literal("gcp").label("provider"),
            func.count().label("connected"),
        )
        .select_from(GCPConnection)
        .where(GCPConnection.tenant_id == tenant_id),
        select(
            literal("saas").label("provider"),
            func.count().label("connected"),
        )
        .select_from(SaaSConnection)
        .where(SaaSConnection.tenant_id == tenant_id),
        select(
            literal("license").label("provider"),
            func.count().label("connected"),
        )
        .select_from(LicenseConnection)
        .where(LicenseConnection.tenant_id == tenant_id),
    )
    counts_subquery = count_rows.subquery()
    counts_result = await db.execute(
        select(counts_subquery.c.provider, counts_subquery.c.connected)
    )
    counts_map = {
        str(row.provider): int(row.connected or 0) for row in counts_result.all()
    }

    return {
        "aws": _usage_item(
            counts_map.get("aws", 0),
            get_tier_limit(tier, "max_aws_accounts"),
        ),
        "azure": _usage_item(
            counts_map.get("azure", 0),
            get_tier_limit(tier, "max_azure_tenants"),
        ),
        "gcp": _usage_item(
            counts_map.get("gcp", 0),
            get_tier_limit(tier, "max_gcp_projects"),
        ),
        "saas": _usage_item(
            counts_map.get("saas", 0),
            get_tier_limit(tier, "max_saas_connections"),
        ),
        "license": _usage_item(
            counts_map.get("license", 0),
            get_tier_limit(tier, "max_license_connections"),
        ),
    }


async def process_paystack_webhook(
    request: Request,
    db: AsyncSession,
    *,
    settings: Any,
    logger: Any,
    extract_client_ip: Callable[[Request], str],
) -> Any:
    from app.modules.billing.domain.billing.paystack_billing import WebhookHandler
    from app.modules.billing.domain.billing.webhook_retry import WebhookRetryService
    import json

    configured_paystack_ips = getattr(settings, "PAYSTACK_WEBHOOK_ALLOWED_IPS", None)
    if isinstance(configured_paystack_ips, (list, tuple, set)):
        paystack_ips = {
            str(ip).strip() for ip in configured_paystack_ips if str(ip).strip()
        }
    elif isinstance(configured_paystack_ips, str):
        paystack_ips = {
            part.strip() for part in configured_paystack_ips.split(",") if part.strip()
        }
    else:
        paystack_ips = set()
    client_ip = extract_client_ip(request)

    if settings.ENVIRONMENT in {"production", "staging"} and client_ip not in paystack_ips:
        logger.warning("unauthorized_webhook_origin", ip=client_ip)
        raise HTTPException(403, "Unauthorized origin IP")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(415, "Unsupported Media Type: expected application/json")

    payload = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    if not signature:
        raise HTTPException(401, "Missing signature")

    handler = WebhookHandler(db)
    if not handler.verify_signature(payload, signature):
        raise HTTPException(401, "Invalid signature")

    data = json.loads(payload)
    event_type = data.get("event", "unknown")
    reference = data.get("data", {}).get("reference", "")

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
        return {"status": "duplicate", "message": "Already queued or processed"}

    try:
        result = await handler.handle(request, payload, signature)
        try:
            await retry_service.mark_inline_processed(job, result)
        except Exception as completion_exc:  # noqa: BLE001
            logger.error(
                "webhook_inline_completion_mark_failed",
                job_id=str(job.id),
                error=str(completion_exc),
            )
        return result
    except Exception as process_error:
        logger.warning(
            "webhook_processing_failed_will_retry",
            job_id=str(job.id),
            error=str(process_error),
        )
        return {"status": "queued", "job_id": str(job.id)}


async def apply_exchange_rate_update(
    db: AsyncSession,
    *,
    rate: float,
    provider: str,
) -> dict[str, Any]:
    from app.models.pricing import ExchangeRate

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.from_currency == "USD", ExchangeRate.to_currency == "NGN"
        )
    )
    rate_obj = result.scalar_one_or_none()

    if rate_obj:
        rate_obj.rate = rate
        rate_obj.provider = provider
        rate_obj.last_updated = datetime.now(timezone.utc)
    else:
        db.add(
            ExchangeRate(
                from_currency="USD",
                to_currency="NGN",
                rate=rate,
                provider=provider,
            )
        )

    await db.commit()
    return {"status": "success", "rate": rate}


async def load_exchange_rate_health(
    db: AsyncSession,
    *,
    logger: Any,
) -> dict[str, Any]:
    from app.models.pricing import ExchangeRate

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
        age_hours = round((now_utc - updated_at).total_seconds() / 3600, 2)
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


async def apply_pricing_plan_update(
    db: AsyncSession,
    *,
    plan_id: str,
    price_usd: float,
    features: Dict[str, Any] | None,
    limits: Dict[str, Any] | None,
) -> dict[str, str]:
    from app.models.pricing import PricingPlan

    result = await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")

    plan.price_usd = price_usd
    if features:
        plan.features = features
    if limits:
        plan.limits = limits

    await db.commit()
    return {"status": "success", "plan_id": plan_id}
