from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.pricing import PricingTier


def fair_use_inflight_key(tenant_id: UUID) -> str:
    return f"llm:fair_use:inflight:{tenant_id}"


def fair_use_global_abuse_block_key() -> str:
    return "llm:fair_use:global_abuse_block"


def fair_use_tier_allowed(tier: PricingTier) -> bool:
    return tier in {PricingTier.PRO, PricingTier.ENTERPRISE}


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return default
    return default


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
    user_id: UUID | None = None,
    actor_type: str | None = None,
) -> int:
    import app.shared.llm.budget_manager as manager_module

    query = select(func.count(manager_module.LLMUsage.id)).where(
        manager_module.LLMUsage.tenant_id == tenant_id,
        manager_module.LLMUsage.created_at >= start,
    )
    normalized_actor_type = str(actor_type or "").strip().lower()
    if normalized_actor_type in {"user", "system"}:
        query = query.where(
            manager_module.LLMUsage.request_type.like(f"{normalized_actor_type}:%")
        )
    if user_id is not None:
        query = query.where(manager_module.LLMUsage.user_id == user_id)
    if end is not None:
        query = query.where(manager_module.LLMUsage.created_at < end)
    result = await db.execute(query)
    return int(result.scalar() or 0)


async def enforce_daily_analysis_limit(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    user_id: UUID | None = None,
    actor_type: str = "system",
) -> None:
    """
    Enforce tier-based per-day LLM analysis quota.

    This guard is evaluated before budget reservation to fail fast on plan limits.
    """
    from app.shared.core.pricing import get_tier_limit
    import app.shared.llm.budget_manager as manager_module

    normalized_actor_type = str(actor_type or "").strip().lower()
    if normalized_actor_type not in {"user", "system"}:
        normalized_actor_type = "user" if user_id is not None else "system"
    if user_id is not None and normalized_actor_type == "system":
        normalized_actor_type = "user"
    if normalized_actor_type == "user" and user_id is None:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="missing_user_actor_context",
            tenant_tier="unknown",
        ).inc()
        raise manager_module.BudgetExceededError(
            "User-scoped LLM request missing actor identity.",
            details={
                "gate": "actor_context",
                "actor_type": normalized_actor_type,
            },
        )

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
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="daily_tenant_limit_exceeded",
            tenant_tier=tier.value,
        ).inc()
        manager_module.audit_log(
            event="llm_quota_denied",
            user_id=str(user_id or "system"),
            tenant_id=str(tenant_id),
            details={
                "gate": "daily_tenant",
                "tier": tier.value,
                "limit": daily_limit,
                "observed": requests_today,
                "actor_type": normalized_actor_type,
            },
        )
        raise manager_module.BudgetExceededError(
            "Daily LLM analysis limit reached for your current plan.",
            details={
                "gate": "daily_tenant",
                "daily_limit": daily_limit,
                "requests_today": requests_today,
                "actor_type": normalized_actor_type,
            },
        )

    if normalized_actor_type == "system":
        raw_system_limit = get_tier_limit(tier, "llm_system_analyses_per_day")
        if raw_system_limit is None:
            return
        try:
            system_daily_limit = int(raw_system_limit)
        except (TypeError, ValueError):
            manager_module.logger.warning(
                "invalid_llm_daily_system_limit",
                tenant_id=str(tenant_id),
                tier=tier.value,
                raw_limit=raw_system_limit,
            )
            return
        if system_daily_limit <= 0:
            manager_module.LLM_PRE_AUTH_DENIALS.labels(
                reason="daily_system_limit_exceeded",
                tenant_tier=tier.value,
            ).inc()
            raise manager_module.BudgetExceededError(
                "System LLM analysis is not available on your current plan.",
                details={
                    "gate": "daily_system",
                    "daily_system_limit": system_daily_limit,
                    "system_requests_today": 0,
                },
            )

        system_requests_today = await count_requests_in_window(
            tenant_id=tenant_id,
            db=db,
            start=day_start,
            end=day_end,
            actor_type="system",
        )
        if system_requests_today >= system_daily_limit:
            manager_module.LLM_PRE_AUTH_DENIALS.labels(
                reason="daily_system_limit_exceeded",
                tenant_tier=tier.value,
            ).inc()
            manager_module.audit_log(
                event="llm_quota_denied",
                user_id="system",
                tenant_id=str(tenant_id),
                details={
                    "gate": "daily_system",
                    "tier": tier.value,
                    "limit": system_daily_limit,
                    "observed": system_requests_today,
                },
            )
            raise manager_module.BudgetExceededError(
                "Daily system LLM analysis limit reached for your current plan.",
                details={
                    "gate": "daily_system",
                    "daily_system_limit": system_daily_limit,
                    "system_requests_today": system_requests_today,
                },
            )
        return

    # Actor normalization above guarantees user_id is present for user-scoped flow.
    user_id = cast(UUID, user_id)

    raw_user_limit = get_tier_limit(tier, "llm_analyses_per_user_per_day")
    if raw_user_limit is None:
        return

    try:
        user_daily_limit = int(raw_user_limit)
    except (TypeError, ValueError):
        manager_module.logger.warning(
            "invalid_llm_daily_user_limit",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            tier=tier.value,
            raw_limit=raw_user_limit,
        )
        return

    if user_daily_limit <= 0:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="daily_user_limit_exceeded",
            tenant_tier=tier.value,
        ).inc()
        manager_module.audit_log(
            event="llm_quota_denied",
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            details={
                "gate": "daily_user",
                "tier": tier.value,
                "limit": user_daily_limit,
                "observed": 0,
            },
        )
        raise manager_module.BudgetExceededError(
            "Daily per-user LLM analysis limit reached for your current plan.",
            details={
                "gate": "daily_user",
                "daily_user_limit": user_daily_limit,
                "user_requests_today": 0,
                "actor_type": normalized_actor_type,
            },
        )

    user_requests_today = await count_requests_in_window(
        tenant_id=tenant_id,
        db=db,
        start=day_start,
        end=day_end,
        user_id=user_id,
        actor_type="user",
    )
    if user_requests_today >= user_daily_limit:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="daily_user_limit_exceeded",
            tenant_tier=tier.value,
        ).inc()
        manager_module.audit_log(
            event="llm_quota_denied",
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            details={
                "gate": "daily_user",
                "tier": tier.value,
                "limit": user_daily_limit,
                "observed": user_requests_today,
            },
        )
        raise manager_module.BudgetExceededError(
            "Daily per-user LLM analysis limit reached for your current plan.",
            details={
                "gate": "daily_user",
                "daily_user_limit": user_daily_limit,
                "user_requests_today": user_requests_today,
                "actor_type": normalized_actor_type,
            },
        )


def _classify_client_ip(client_ip: str | None) -> tuple[str, int]:
    raw = str(client_ip or "").strip()
    if not raw:
        return "unknown", 50
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        return "invalid", 80
    if parsed.is_loopback:
        return "loopback", 75
    if parsed.is_link_local:
        return "link_local", 65
    if parsed.is_private:
        return "private", 40
    if parsed.is_reserved or parsed.is_multicast:
        return "reserved", 70
    if parsed.version == 4:
        return "public_v4", 20
    return "public_v6", 20


async def record_authenticated_abuse_signal(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    tier: PricingTier,
    actor_type: str,
    user_id: UUID | None,
    client_ip: str | None,
) -> None:
    import app.shared.llm.budget_manager as manager_module

    del manager_cls
    del db
    normalized_actor_type = str(actor_type or "").strip().lower()
    if normalized_actor_type not in {"user", "system"}:
        normalized_actor_type = "user" if user_id is not None else "system"
    if user_id is not None and normalized_actor_type == "system":
        normalized_actor_type = "user"
    ip_bucket, risk_score = _classify_client_ip(client_ip)
    manager_module.LLM_AUTH_ABUSE_SIGNALS.labels(
        tenant_tier=tier.value,
        actor_type=normalized_actor_type,
        ip_bucket=ip_bucket,
    ).inc()
    manager_module.LLM_AUTH_IP_RISK_SCORE.labels(
        tenant_tier=tier.value,
        actor_type=normalized_actor_type,
    ).set(risk_score)

    if risk_score < 70:
        return

    manager_module.audit_log(
        event="llm_authenticated_abuse_signal",
        user_id=str(user_id or "system"),
        tenant_id=str(tenant_id),
        details={
            "actor_type": normalized_actor_type,
            "ip_bucket": ip_bucket,
            "risk_score": risk_score,
        },
    )


async def enforce_global_abuse_guard(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    tier: PricingTier,
) -> None:
    import app.shared.llm.budget_manager as manager_module

    settings = manager_module.get_settings()
    if not _as_bool(
        getattr(settings, "LLM_GLOBAL_ABUSE_GUARDS_ENABLED", True),
        default=True,
    ):
        return

    tier_label = tier.value
    kill_switch_enabled = _as_bool(
        getattr(settings, "LLM_GLOBAL_ABUSE_KILL_SWITCH", False),
        default=False,
    )
    if kill_switch_enabled:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="global_abuse_kill_switch",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_DENIALS.labels(
            gate="global_abuse",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="global_abuse", outcome="deny", tenant_tier=tier_label
        ).inc()
        raise manager_module.LLMFairUseExceededError(
            "Global abuse protections are active. LLM analysis is temporarily unavailable.",
            details={
                "gate": "global_abuse",
                "reason": "kill_switch",
            },
        )

    block_key = fair_use_global_abuse_block_key()
    block_seconds_raw = getattr(settings, "LLM_GLOBAL_ABUSE_BLOCK_SECONDS", 120)
    block_seconds = max(30, _as_int(block_seconds_raw, default=120))
    cache = manager_module.get_cache_service()
    local_until = getattr(manager_cls, "_local_global_abuse_block_until", None)
    now = datetime.now(timezone.utc)
    if isinstance(local_until, datetime) and local_until > now:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="global_abuse_temporal_block",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_DENIALS.labels(
            gate="global_abuse",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="global_abuse", outcome="deny", tenant_tier=tier_label
        ).inc()
        raise manager_module.LLMFairUseExceededError(
            "Global abuse protections are active. Retry shortly.",
            details={
                "gate": "global_abuse",
                "reason": "temporal_block",
                "retry_after_seconds": int((local_until - now).total_seconds()),
            },
        )
    if cache.enabled and cache.client is not None:
        try:
            get_fn = getattr(cache.client, "get", None)
            if callable(get_fn) and await get_fn(block_key):
                manager_module.LLM_PRE_AUTH_DENIALS.labels(
                    reason="global_abuse_temporal_block",
                    tenant_tier=tier_label,
                ).inc()
                manager_module.LLM_FAIR_USE_DENIALS.labels(
                    gate="global_abuse",
                    tenant_tier=tier_label,
                ).inc()
                manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
                    gate="global_abuse", outcome="deny", tenant_tier=tier_label
                ).inc()
                raise manager_module.LLMFairUseExceededError(
                    "Global abuse protections are active. Retry shortly.",
                    details={
                        "gate": "global_abuse",
                        "reason": "temporal_block",
                        "retry_after_seconds": block_seconds,
                    },
                )
        except manager_module.LLMFairUseExceededError:
            raise
        except Exception as exc:
            manager_module.logger.warning(
                "llm_global_abuse_cache_get_failed",
                error=str(exc),
            )

    minute_start = now - timedelta(minutes=1)
    stmt = select(
        func.count(manager_module.LLMUsage.id),
        func.count(func.distinct(manager_module.LLMUsage.tenant_id)),
    ).where(manager_module.LLMUsage.created_at >= minute_start)
    result = await db.execute(stmt)
    row: Any = None
    row_getter = getattr(result, "one_or_none", None)
    if callable(row_getter):
        row = row_getter()
    if row is None:
        first_getter = getattr(result, "first", None)
        if callable(first_getter):
            row = first_getter()
    if row is None:
        row = (0, 0)
    try:
        global_requests_last_minute = int((row[0] if row else 0) or 0)
    except Exception:
        global_requests_last_minute = 0
    try:
        active_tenants_last_minute = int((row[1] if row else 0) or 0)
    except Exception:
        active_tenants_last_minute = 0

    manager_module.LLM_FAIR_USE_OBSERVED.labels(
        gate="global_rpm", tenant_tier=tier_label
    ).set(global_requests_last_minute)
    manager_module.LLM_FAIR_USE_OBSERVED.labels(
        gate="global_tenant_count", tenant_tier=tier_label
    ).set(active_tenants_last_minute)

    rpm_threshold_raw = getattr(settings, "LLM_GLOBAL_ABUSE_PER_MINUTE_CAP", 600)
    tenant_threshold_raw = getattr(
        settings, "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD", 30
    )
    rpm_threshold = max(1, _as_int(rpm_threshold_raw, default=600))
    tenant_threshold = max(1, _as_int(tenant_threshold_raw, default=30))

    triggered = (
        global_requests_last_minute >= rpm_threshold
        and active_tenants_last_minute >= tenant_threshold
    )
    if triggered:
        manager_module.LLM_PRE_AUTH_DENIALS.labels(
            reason="global_abuse_triggered",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_DENIALS.labels(
            gate="global_abuse",
            tenant_tier=tier_label,
        ).inc()
        manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
            gate="global_abuse", outcome="deny", tenant_tier=tier_label
        ).inc()
        manager_module.audit_log(
            event="llm_global_abuse_triggered",
            user_id="system",
            tenant_id=str(tenant_id),
            details={
                "gate": "global_abuse",
                "global_requests_last_minute": global_requests_last_minute,
                "active_tenants_last_minute": active_tenants_last_minute,
                "rpm_threshold": rpm_threshold,
                "tenant_threshold": tenant_threshold,
                "block_seconds": block_seconds,
            },
        )
        manager_cls._local_global_abuse_block_until = now + timedelta(
            seconds=block_seconds
        )
        if cache.enabled and cache.client is not None:
            try:
                set_fn = getattr(cache.client, "set", None)
                if callable(set_fn):
                    await set_fn(block_key, "1", ex=block_seconds)
            except Exception as exc:
                manager_module.logger.warning(
                    "llm_global_abuse_cache_set_failed",
                    error=str(exc),
                )
        raise manager_module.LLMFairUseExceededError(
            "Global anti-abuse throttle is active. Retry shortly.",
            details={
                "gate": "global_abuse",
                "reason": "burst_detected",
                "global_requests_last_minute": global_requests_last_minute,
                "active_tenants_last_minute": active_tenants_last_minute,
                "rpm_threshold": rpm_threshold,
                "tenant_threshold": tenant_threshold,
                "retry_after_seconds": block_seconds,
            },
        )

    manager_module.LLM_FAIR_USE_EVALUATIONS.labels(
        gate="global_abuse", outcome="allow", tenant_tier=tier_label
    ).inc()


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
