from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.pricing import PricingTier


def fair_use_inflight_key(tenant_id: UUID) -> str:
    return f"llm:fair_use:inflight:{tenant_id}"


def fair_use_tier_allowed(tier: PricingTier) -> bool:
    return tier in {PricingTier.PRO, PricingTier.ENTERPRISE}


def fair_use_daily_soft_cap(tier: PricingTier) -> int | None:
    import app.shared.llm.budget_manager as manager_module

    settings = manager_module.get_settings()
    cap_map = {
        PricingTier.PRO: settings.LLM_FAIR_USE_PRO_DAILY_SOFT_CAP,
        PricingTier.ENTERPRISE: settings.LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP,
    }
    cap = cap_map.get(tier)
    if cap is None:
        return None
    try:
        cap_int = int(cap)
    except (TypeError, ValueError):
        return None
    return cap_int if cap_int > 0 else None


async def count_requests_in_window(
    tenant_id: UUID,
    db: AsyncSession,
    start: datetime,
    end: datetime | None = None,
) -> int:
    import app.shared.llm.budget_manager as manager_module

    query = select(func.count(manager_module.LLMUsage.id)).where(
        manager_module.LLMUsage.tenant_id == tenant_id,
        manager_module.LLMUsage.created_at >= start,
    )
    if end is not None:
        query = query.where(manager_module.LLMUsage.created_at < end)
    result = await db.execute(query)
    return int(result.scalar() or 0)


async def enforce_daily_analysis_limit(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
) -> None:
    """
    Enforce tier-based per-day LLM analysis quota.

    This guard is evaluated before budget reservation to fail fast on plan limits.
    """
    from app.shared.core.pricing import get_tier_limit
    import app.shared.llm.budget_manager as manager_module

    tier = await manager_module.get_tenant_tier(tenant_id, db)
    raw_limit = get_tier_limit(tier, "llm_analyses_per_day")
    if raw_limit is None:
        return

    try:
        daily_limit = int(raw_limit)
    except (TypeError, ValueError):
        manager_module.logger.warning(
            "invalid_llm_daily_limit",
            tenant_id=str(tenant_id),
            tier=tier.value,
            raw_limit=raw_limit,
        )
        return

    if daily_limit <= 0:
        raise manager_module.BudgetExceededError(
            "LLM analysis is not available on your current plan.",
            details={"daily_limit": daily_limit, "requests_today": 0},
        )

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    requests_today = await count_requests_in_window(
        tenant_id=tenant_id,
        db=db,
        start=day_start,
        end=day_end,
    )
    if requests_today >= daily_limit:
        raise manager_module.BudgetExceededError(
            "Daily LLM analysis limit reached for your current plan.",
            details={
                "daily_limit": daily_limit,
                "requests_today": requests_today,
            },
        )


async def acquire_fair_use_inflight_slot(
    manager_cls: Any,
    tenant_id: UUID,
    max_inflight: int,
    ttl_seconds: int,
) -> tuple[bool, int]:
    """Acquire one in-flight request slot for a tenant."""
    import app.shared.llm.budget_manager as manager_module

    key = fair_use_inflight_key(tenant_id)

    cache = manager_module.get_cache_service()
    if cache.enabled and cache.client is not None:
        try:
            client = cache.client
            incr = getattr(client, "incr", None)
            decr = getattr(client, "decr", None)
            expire = getattr(client, "expire", None)
            if callable(incr) and callable(decr):
                current = int(await incr(key))
                if callable(expire):
                    await expire(key, ttl_seconds)
                if current > max_inflight:
                    await decr(key)
                    return False, max(current - 1, 0)
                return True, current
        except Exception as exc:
            manager_module.logger.warning(
                "llm_fair_use_redis_acquire_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )

    async with manager_cls._local_inflight_lock:
        current = manager_cls._local_inflight_counts.get(key, 0) + 1
        manager_cls._local_inflight_counts[key] = current
        if current > max_inflight:
            next_value = current - 1
            if next_value <= 0:
                manager_cls._local_inflight_counts.pop(key, None)
            else:
                manager_cls._local_inflight_counts[key] = next_value
            return False, max(next_value, 0)
        return True, current


async def release_fair_use_inflight_slot(manager_cls: Any, tenant_id: UUID) -> None:
    """Best-effort release for one in-flight request slot."""
    import app.shared.llm.budget_manager as manager_module

    key = fair_use_inflight_key(tenant_id)
    if not manager_module.get_settings().LLM_FAIR_USE_GUARDS_ENABLED:
        async with manager_cls._local_inflight_lock:
            manager_cls._local_inflight_counts.pop(key, None)
        return

    cache = manager_module.get_cache_service()
    if cache.enabled and cache.client is not None:
        try:
            decr = getattr(cache.client, "decr", None)
            if callable(decr):
                current = int(await decr(key))
                if current < 0:
                    set_fn = getattr(cache.client, "set", None)
                    if callable(set_fn):
                        await set_fn(key, "0", ex=60)
                return
        except Exception as exc:
            manager_module.logger.warning(
                "llm_fair_use_redis_release_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )

    async with manager_cls._local_inflight_lock:
        current = manager_cls._local_inflight_counts.get(key, 0)
        if current <= 1:
            manager_cls._local_inflight_counts.pop(key, None)
        else:
            manager_cls._local_inflight_counts[key] = current - 1


async def enforce_fair_use_guards(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    tier: PricingTier,
) -> bool:
    """
    Optional fair-use guardrails for future near-unlimited tiers.

    Returns True when a concurrency slot is acquired and must be released.
    """
    import app.shared.llm.budget_manager as manager_module

    settings = manager_module.get_settings()
    tier_label = tier.value
    if not settings.LLM_FAIR_USE_GUARDS_ENABLED:
        return False
    if not fair_use_tier_allowed(tier):
        return False

    now = datetime.now(timezone.utc)

    daily_soft_cap = fair_use_daily_soft_cap(tier)
    if daily_soft_cap is not None:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        requests_today = await count_requests_in_window(
            tenant_id=tenant_id, db=db, start=day_start, end=day_end
        )
        manager_module.LLM_FAIR_USE_OBSERVED.labels(
            gate="soft_daily", tenant_tier=tier_label
        ).set(requests_today)
        if requests_today >= daily_soft_cap:
            manager_module.LLM_PRE_AUTH_DENIALS.labels(
                reason="fair_use_soft_daily", tenant_tier=tier_label
            ).inc()
            manager_module.LLM_FAIR_USE_DENIALS.labels(
                gate="soft_daily", tenant_tier=tier_label
            ).inc()
            manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
                gate="soft_daily", outcome="deny", tenant_tier=tier_label
            ).inc()
            manager_module.audit_log(
                event="llm_fair_use_denied",
                user_id="system",
                tenant_id=str(tenant_id),
                details={
                    "gate": "soft_daily",
                    "tier": tier_label,
                    "limit": daily_soft_cap,
                    "observed": requests_today,
                },
            )
            raise manager_module.LLMFairUseExceededError(
                "Daily fair-use limit reached. Retry tomorrow or contact support to increase limits.",
                details={
                    "gate": "soft_daily",
                    "limit": daily_soft_cap,
                    "observed": requests_today,
                    "recommendation": "upgrade_or_contact_support",
                },
            )
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="soft_daily", outcome="allow", tenant_tier=tier_label
        ).inc()

    try:
        per_minute_cap = int(settings.LLM_FAIR_USE_PER_MINUTE_CAP)
    except (TypeError, ValueError):
        per_minute_cap = 0
    if per_minute_cap > 0:
        minute_start = now - timedelta(minutes=1)
        requests_last_minute = await count_requests_in_window(
            tenant_id=tenant_id, db=db, start=minute_start
        )
        manager_module.LLM_FAIR_USE_OBSERVED.labels(
            gate="per_minute", tenant_tier=tier_label
        ).set(requests_last_minute)
        if requests_last_minute >= per_minute_cap:
            manager_module.LLM_PRE_AUTH_DENIALS.labels(
                reason="fair_use_per_minute", tenant_tier=tier_label
            ).inc()
            manager_module.LLM_FAIR_USE_DENIALS.labels(
                gate="per_minute", tenant_tier=tier_label
            ).inc()
            manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
                gate="per_minute", outcome="deny", tenant_tier=tier_label
            ).inc()
            manager_module.audit_log(
                event="llm_fair_use_denied",
                user_id="system",
                tenant_id=str(tenant_id),
                details={
                    "gate": "per_minute",
                    "tier": tier_label,
                    "limit": per_minute_cap,
                    "observed": requests_last_minute,
                },
            )
            raise manager_module.LLMFairUseExceededError(
                "Rate limit reached for this tenant. Retry in about 60 seconds or contact support for higher throughput.",
                details={
                    "gate": "per_minute",
                    "limit": per_minute_cap,
                    "observed": requests_last_minute,
                    "retry_after_seconds": 60,
                    "recommendation": "upgrade_or_contact_support",
                },
            )
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="per_minute", outcome="allow", tenant_tier=tier_label
        ).inc()

    try:
        max_concurrency = int(settings.LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP)
    except (TypeError, ValueError):
        max_concurrency = 0
    if max_concurrency <= 0:
        return False

    try:
        lease_ttl = int(settings.LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS)
    except (TypeError, ValueError):
        lease_ttl = 180

    acquired, current_inflight = await acquire_fair_use_inflight_slot(
        manager_cls=manager_cls,
        tenant_id=tenant_id,
        max_inflight=max_concurrency,
        ttl_seconds=max(30, lease_ttl),
    )
    manager_module.LLM_FAIR_USE_OBSERVED.labels(
        gate="concurrency", tenant_tier=tier_label
    ).set(current_inflight)
    if not acquired:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="fair_use_concurrency", tenant_tier=tier_label
        ).inc()
        manager_module.LLM_FAIR_USE_DENIALS.labels(
            gate="concurrency", tenant_tier=tier_label
        ).inc()
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="concurrency", outcome="deny", tenant_tier=tier_label
        ).inc()
        manager_module.audit_log(
            event="llm_fair_use_denied",
            user_id="system",
            tenant_id=str(tenant_id),
            details={
                "gate": "concurrency",
                "tier": tier_label,
                "limit": max_concurrency,
                "observed": current_inflight,
            },
        )
        raise manager_module.LLMFairUseExceededError(
            "Too many in-flight LLM requests for this tenant. Retry shortly or contact support for higher throughput.",
            details={
                "gate": "concurrency",
                "limit": max_concurrency,
                "observed": current_inflight,
                "retry_after_seconds": max(5, min(lease_ttl, 60)),
                "recommendation": "upgrade_or_contact_support",
            },
        )
    manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
        gate="concurrency", outcome="allow", tenant_tier=tier_label
    ).inc()
    return True
