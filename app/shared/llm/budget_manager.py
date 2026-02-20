"""
LLM Budget Management Service

PRODUCTION: Ensures LLM requests are pre-authorized and within budget limits.
Implements atomic budget reservation/debit pattern to prevent cost overages.
"""

import structlog
import asyncio
import inspect
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from uuid import UUID
from enum import Enum
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.llm import LLMBudget, LLMUsage
from app.shared.core.exceptions import BudgetExceededError, LLMFairUseExceededError
from app.shared.llm.pricing_data import LLM_PRICING
from app.shared.llm.pricing_data import ProviderCost
from app.shared.core.cache import get_cache_service
from app.shared.core.config import get_settings

# Moved BudgetStatus here
from app.shared.core.ops_metrics import (
    LLM_PRE_AUTH_DENIALS,
    LLM_SPEND_USD,
    LLM_FAIR_USE_DENIALS,
    LLM_FAIR_USE_EVALUATIONS,
    LLM_FAIR_USE_OBSERVED,
)
from app.shared.core.pricing import get_tenant_tier, PricingTier
from app.shared.core.logging import audit_log

logger = structlog.get_logger()


class BudgetStatus(str, Enum):
    OK = "ok"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"


class LLMBudgetManager:
    """
    Thread-safe budget management with atomic operations.

    Guarantees:
    1. No request executes without pre-authorization
    2. Budget state is always consistent (no double-spending)
    3. All operations are logged for audit trail
    """

    # Conservative estimate: 1 prompt ≈ 500 tokens
    AVG_PROMPT_TOKENS = 500
    AVG_RESPONSE_TOKENS = 500

    # BYOK policy: no surcharge; platform pricing is tier-based.
    BYOK_PLATFORM_FEE_USD = Decimal("0.00")
    _local_inflight_counts: dict[str, int] = {}
    _local_inflight_lock = asyncio.Lock()

    @staticmethod
    def _to_decimal(v: Any) -> Decimal:
        """Safe conversion to Decimal for currency math."""
        if v is None:
            return Decimal("0")
        try:
            return Decimal(str(v))
        except (ValueError, TypeError, InvalidOperation):
            logger.warning("invalid_decimal_conversion", value=str(v))
            return Decimal("0")

    @classmethod
    def estimate_cost(
        cls,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        provider: str = "openai",
    ) -> Decimal:
        """
        Estimate LLM request cost in USD using shared pricing data.
        """
        # Find pricing data for provider and model
        provider_data = LLM_PRICING.get(provider, {})
        pricing = provider_data.get(model)

        # PRODUCTION: Fallback to provider default if model is unknown
        if not pricing:
            pricing = provider_data.get("default")

        # PRODUCTION: Global Fallback ($10 per 1M tokens) if still not found
        if not pricing:
            logger.warning(
                "llm_pricing_using_global_fallback", provider=provider, model=model
            )
            pricing = ProviderCost(input=10.0, output=10.0, free_tier_tokens=0)

        # Calculate cost
        input_cost = (
            Decimal(str(prompt_tokens)) * Decimal(str(pricing["input"]))
        ) / Decimal("1000000")
        output_cost = (
            Decimal(str(completion_tokens)) * Decimal(str(pricing["output"]))
        ) / Decimal("1000000")

        return (input_cost + output_cost).quantize(Decimal("0.0001"))

    @classmethod
    async def _enforce_daily_analysis_limit(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Enforce tier-based per-day LLM analysis quota.

        This guard is evaluated before budget reservation to fail fast on plan limits.
        """
        from app.shared.core.pricing import get_tier_limit

        tier = await get_tenant_tier(tenant_id, db)
        raw_limit = get_tier_limit(tier, "llm_analyses_per_day")
        if raw_limit is None:
            return

        try:
            daily_limit = int(raw_limit)
        except (TypeError, ValueError):
            logger.warning(
                "invalid_llm_daily_limit",
                tenant_id=str(tenant_id),
                tier=tier.value,
                raw_limit=raw_limit,
            )
            return

        if daily_limit <= 0:
            raise BudgetExceededError(
                "LLM analysis is not available on your current plan.",
                details={"daily_limit": daily_limit, "requests_today": 0},
            )

        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        result = await db.execute(
            select(func.count(LLMUsage.id)).where(
                LLMUsage.tenant_id == tenant_id,
                LLMUsage.created_at >= day_start,
                LLMUsage.created_at < day_end,
            )
        )
        requests_today = int(result.scalar() or 0)
        if requests_today >= daily_limit:
            raise BudgetExceededError(
                "Daily LLM analysis limit reached for your current plan.",
                details={
                    "daily_limit": daily_limit,
                    "requests_today": requests_today,
                },
            )

    @staticmethod
    def _fair_use_inflight_key(tenant_id: UUID) -> str:
        return f"llm:fair_use:inflight:{tenant_id}"

    @staticmethod
    def _fair_use_tier_allowed(tier: PricingTier) -> bool:
        return tier in {PricingTier.PRO, PricingTier.ENTERPRISE}

    @staticmethod
    def _fair_use_daily_soft_cap(tier: PricingTier) -> int | None:
        settings = get_settings()
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

    @staticmethod
    async def _count_requests_in_window(
        tenant_id: UUID,
        db: AsyncSession,
        start: datetime,
        end: datetime | None = None,
    ) -> int:
        query = select(func.count(LLMUsage.id)).where(
            LLMUsage.tenant_id == tenant_id,
            LLMUsage.created_at >= start,
        )
        if end is not None:
            query = query.where(LLMUsage.created_at < end)
        result = await db.execute(query)
        return int(result.scalar() or 0)

    @classmethod
    async def _acquire_fair_use_inflight_slot(
        cls, tenant_id: UUID, max_inflight: int, ttl_seconds: int
    ) -> tuple[bool, int]:
        """Acquire one in-flight request slot for a tenant."""
        key = cls._fair_use_inflight_key(tenant_id)

        cache = get_cache_service()
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
                logger.warning(
                    "llm_fair_use_redis_acquire_failed",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )

        async with cls._local_inflight_lock:
            current = cls._local_inflight_counts.get(key, 0) + 1
            cls._local_inflight_counts[key] = current
            if current > max_inflight:
                next_value = current - 1
                if next_value <= 0:
                    cls._local_inflight_counts.pop(key, None)
                else:
                    cls._local_inflight_counts[key] = next_value
                return False, max(next_value, 0)
            return True, current

    @classmethod
    async def _release_fair_use_inflight_slot(cls, tenant_id: UUID) -> None:
        """Best-effort release for one in-flight request slot."""
        key = cls._fair_use_inflight_key(tenant_id)
        if not get_settings().LLM_FAIR_USE_GUARDS_ENABLED:
            async with cls._local_inflight_lock:
                cls._local_inflight_counts.pop(key, None)
            return

        cache = get_cache_service()
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
                logger.warning(
                    "llm_fair_use_redis_release_failed",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )

        async with cls._local_inflight_lock:
            current = cls._local_inflight_counts.get(key, 0)
            if current <= 1:
                cls._local_inflight_counts.pop(key, None)
            else:
                cls._local_inflight_counts[key] = current - 1

    @classmethod
    async def _enforce_fair_use_guards(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        tier: PricingTier,
    ) -> bool:
        """
        Optional fair-use guardrails for future near-unlimited tiers.

        Returns True when a concurrency slot is acquired and must be released.
        """
        settings = get_settings()
        tier_label = tier.value
        if not settings.LLM_FAIR_USE_GUARDS_ENABLED:
            return False
        if not cls._fair_use_tier_allowed(tier):
            return False

        now = datetime.now(timezone.utc)

        daily_soft_cap = cls._fair_use_daily_soft_cap(tier)
        if daily_soft_cap is not None:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            requests_today = await cls._count_requests_in_window(
                tenant_id=tenant_id, db=db, start=day_start, end=day_end
            )
            LLM_FAIR_USE_OBSERVED.labels(gate="soft_daily", tenant_tier=tier_label).set(
                requests_today
            )
            if requests_today >= daily_soft_cap:
                LLM_PRE_AUTH_DENIALS.labels(
                    reason="fair_use_soft_daily", tenant_tier=tier_label
                ).inc()
                LLM_FAIR_USE_DENIALS.labels(
                    gate="soft_daily", tenant_tier=tier_label
                ).inc()
                LLM_FAIR_USE_EVALUATIONS.labels(
                    gate="soft_daily", outcome="deny", tenant_tier=tier_label
                ).inc()
                audit_log(
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
                raise LLMFairUseExceededError(
                    "Daily fair-use limit reached. Retry tomorrow or contact support to increase limits.",
                    details={
                        "gate": "soft_daily",
                        "limit": daily_soft_cap,
                        "observed": requests_today,
                        "recommendation": "upgrade_or_contact_support",
                    },
                )
            LLM_FAIR_USE_EVALUATIONS.labels(
                gate="soft_daily", outcome="allow", tenant_tier=tier_label
            ).inc()

        try:
            per_minute_cap = int(settings.LLM_FAIR_USE_PER_MINUTE_CAP)
        except (TypeError, ValueError):
            per_minute_cap = 0
        if per_minute_cap > 0:
            minute_start = now - timedelta(minutes=1)
            requests_last_minute = await cls._count_requests_in_window(
                tenant_id=tenant_id, db=db, start=minute_start
            )
            LLM_FAIR_USE_OBSERVED.labels(gate="per_minute", tenant_tier=tier_label).set(
                requests_last_minute
            )
            if requests_last_minute >= per_minute_cap:
                LLM_PRE_AUTH_DENIALS.labels(
                    reason="fair_use_per_minute", tenant_tier=tier_label
                ).inc()
                LLM_FAIR_USE_DENIALS.labels(
                    gate="per_minute", tenant_tier=tier_label
                ).inc()
                LLM_FAIR_USE_EVALUATIONS.labels(
                    gate="per_minute", outcome="deny", tenant_tier=tier_label
                ).inc()
                audit_log(
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
                raise LLMFairUseExceededError(
                    "Rate limit reached for this tenant. Retry in about 60 seconds or contact support for higher throughput.",
                    details={
                        "gate": "per_minute",
                        "limit": per_minute_cap,
                        "observed": requests_last_minute,
                        "retry_after_seconds": 60,
                        "recommendation": "upgrade_or_contact_support",
                    },
                )
            LLM_FAIR_USE_EVALUATIONS.labels(
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

        acquired, current_inflight = await cls._acquire_fair_use_inflight_slot(
            tenant_id=tenant_id,
            max_inflight=max_concurrency,
            ttl_seconds=max(30, lease_ttl),
        )
        LLM_FAIR_USE_OBSERVED.labels(gate="concurrency", tenant_tier=tier_label).set(
            current_inflight
        )
        if not acquired:
            LLM_PRE_AUTH_DENIALS.labels(
                reason="fair_use_concurrency", tenant_tier=tier_label
            ).inc()
            LLM_FAIR_USE_DENIALS.labels(
                gate="concurrency", tenant_tier=tier_label
            ).inc()
            LLM_FAIR_USE_EVALUATIONS.labels(
                gate="concurrency", outcome="deny", tenant_tier=tier_label
            ).inc()
            audit_log(
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
            raise LLMFairUseExceededError(
                "Too many in-flight LLM requests for this tenant. Retry shortly or contact support for higher throughput.",
                details={
                    "gate": "concurrency",
                    "limit": max_concurrency,
                    "observed": current_inflight,
                    "retry_after_seconds": max(5, min(lease_ttl, 60)),
                    "recommendation": "upgrade_or_contact_support",
                },
            )
        LLM_FAIR_USE_EVALUATIONS.labels(
            gate="concurrency", outcome="allow", tenant_tier=tier_label
        ).inc()
        return True

    @classmethod
    async def check_and_reserve(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        provider: str = "openai",
        model: str = "gpt-4o",
        prompt_tokens: int = AVG_PROMPT_TOKENS,
        completion_tokens: int = AVG_RESPONSE_TOKENS,
        operation_id: str | None = None,
    ) -> Decimal:
        """
        PRODUCTION: Check budget and atomically reserve funds.
        """
        estimated_cost = cls.estimate_cost(
            prompt_tokens, completion_tokens, model, provider
        )
        concurrency_slot_acquired = False
        tier_for_metrics = "unknown"

        try:
            # 0. Enforce plan-level daily LLM request quota.
            await cls._enforce_daily_analysis_limit(tenant_id, db)
            if get_settings().LLM_FAIR_USE_GUARDS_ENABLED:
                tier = await get_tenant_tier(tenant_id, db)
                tier_for_metrics = tier.value
                concurrency_slot_acquired = await cls._enforce_fair_use_guards(
                    tenant_id=tenant_id,
                    db=db,
                    tier=tier,
                )

            # 1. Fetch current budget state (with FOR UPDATE lock)
            result = await db.execute(
                select(LLMBudget)
                .where(LLMBudget.tenant_id == tenant_id)
                .with_for_update()
            )
            budget = result.scalar_one_or_none()

            if not budget:
                tier = await get_tenant_tier(tenant_id, db)
                default_limit = Decimal("1.00")
                if tier in {PricingTier.STARTER, PricingTier.GROWTH}:
                    default_limit = Decimal("10.00")
                elif tier in {PricingTier.PRO, PricingTier.ENTERPRISE}:
                    default_limit = Decimal("50.00")

                budget = LLMBudget(
                    tenant_id=tenant_id,
                    monthly_limit_usd=float(default_limit),
                    alert_threshold_percent=80,
                    hard_limit=True,
                    preferred_provider="groq",
                    preferred_model="llama-3.3-70b-versatile",
                )
                db.add(budget)
                await db.flush()
                logger.info(
                    "budget_auto_bootstrapped",
                    tenant_id=str(tenant_id),
                    tier=tier.value,
                    monthly_limit_usd=float(default_limit),
                )

            # 2. Handle month-rollover logic (Finding #S2)
            now = datetime.now(timezone.utc)
            if (
                budget.budget_reset_at.year != now.year
                or budget.budget_reset_at.month != now.month
            ):
                logger.info(
                    "llm_budget_month_reset",
                    tenant_id=str(tenant_id),
                    old_reset=budget.budget_reset_at.isoformat(),
                    new_reset=now.isoformat(),
                    previous_spend=float(budget.monthly_spend_usd),
                )
                budget.monthly_spend_usd = Decimal("0.0")
                budget.pending_reservations_usd = Decimal("0.0")
                budget.budget_reset_at = now
                # We don't need to commit yet, as we are in the same transaction

            # 3. Enforce hard limit using atomic counters
            limit = cls._to_decimal(budget.monthly_limit_usd)
            current_total = budget.monthly_spend_usd + budget.pending_reservations_usd
            remaining_budget = limit - current_total

            if estimated_cost > remaining_budget:
                logger.warning(
                    "llm_budget_exceeded",
                    tenant_id=str(tenant_id),
                    model=model,
                    estimated_cost=float(estimated_cost),
                    remaining_budget=float(remaining_budget),
                    monthly_limit=float(limit),
                    current_total_committed=float(current_total),
                )

                # Emit metric for alerting
                LLM_PRE_AUTH_DENIALS.labels(
                    reason="hard_limit_exceeded", tenant_tier=tier_for_metrics
                ).inc()

                raise BudgetExceededError(
                    f"LLM budget exceeded. Required: ${float(estimated_cost):.4f}, Available: ${float(remaining_budget):.4f}",
                    details={
                        "monthly_limit": float(limit),
                        "current_total_committed": float(current_total),
                        "estimated_cost": float(estimated_cost),
                        "remaining_budget": float(remaining_budget),
                        "model": model,
                    },
                )

            # 4. Atomic Increment of Pending Reservations
            budget.pending_reservations_usd += estimated_cost
            await db.flush()  # Ensure sync to DB state before proceeding

            logger.info(
                "llm_budget_reserved",
                tenant_id=str(tenant_id),
                model=model,
                reserved_amount=float(estimated_cost),
                new_pending_total=float(budget.pending_reservations_usd),
                operation_id=operation_id,
            )

            return estimated_cost

        except BudgetExceededError:
            if concurrency_slot_acquired:
                await cls._release_fair_use_inflight_slot(tenant_id)
            raise
        except Exception as e:
            if concurrency_slot_acquired:
                await cls._release_fair_use_inflight_slot(tenant_id)
            logger.exception(
                "budget_check_failed",
                tenant_id=str(tenant_id),
                model=model,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    @classmethod
    async def record_usage(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider: str = "openai",
        actual_cost_usd: Decimal | None = None,
        is_byok: bool = False,
        operation_id: str | None = None,
        request_type: str = "unknown",
    ) -> None:
        """
        Record actual LLM usage and handle metrics/alerts.
        """
        try:
            # 1. Fetch budget for update to ensure atomic debit
            # Note: We assume the reservation was already made by check_and_reserve
            result = await db.execute(
                select(LLMBudget)
                .where(LLMBudget.tenant_id == tenant_id)
                .with_for_update()
            )
            budget = result.scalar_one_or_none()

            if is_byok:
                actual_cost_usd = cls.BYOK_PLATFORM_FEE_USD
            elif actual_cost_usd is None:
                actual_cost_usd = cls.estimate_cost(
                    prompt_tokens, completion_tokens, model, provider
                )

            actual_cost_decimal = cls._to_decimal(actual_cost_usd)

            if budget:
                # 2. Atomic Transition: Reservation -> Hard Spend
                # We subtract the reservation estimate (approximated here if not passed back)
                # and add the actual cost.
                # For simplicity, we decrement pending_reservations_usd by the estimate
                # and increment monthly_spend_usd by actual.

                # We need the original reservation to be perfect, but since we don't store
                # per-request reservation IDs in the DB table yet, we perform a safe decrement.
                estimated_reservation = cls.estimate_cost(
                    prompt_tokens, completion_tokens, model, provider
                )

                budget.pending_reservations_usd = max(
                    Decimal("0.0"),
                    budget.pending_reservations_usd - estimated_reservation,
                )
                budget.monthly_spend_usd += actual_cost_decimal
                await db.flush()

            # Create usage record
            usage = LLMUsage(
                tenant_id=tenant_id,
                provider=provider,
                model=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=actual_cost_decimal,
                is_byok=is_byok,
                operation_id=operation_id,
                request_type=request_type,
            )
            db.add(usage)

            # Metrics
            try:
                tier = await get_tenant_tier(tenant_id, db)
                LLM_SPEND_USD.labels(
                    tenant_tier=tier.value, provider=provider, model=model
                ).inc(float(actual_cost_usd))
            except Exception as e:
                logger.debug("llm_spend_metric_inc_failed", error=str(e), exc_info=True)

            await db.flush()
            await db.commit()

            # Handle alerts
            await cls._check_budget_and_alert(tenant_id, db, actual_cost_usd)

            logger.info(
                "llm_usage_recorded",
                tenant_id=str(tenant_id),
                model=model,
                tokens_total=prompt_tokens + completion_tokens,
                cost=float(actual_cost_usd),
                operation_id=operation_id,
            )

        except Exception as e:
            logger.error(
                "usage_recording_failed",
                tenant_id=str(tenant_id),
                model=model,
                error=str(e),
                error_type=type(e).__name__,
            )
            rollback_fn = getattr(db, "rollback", None)
            if callable(rollback_fn):
                try:
                    rollback_result = rollback_fn()
                    if inspect.isawaitable(rollback_result):
                        await rollback_result
                except Exception as rollback_exc:
                    logger.warning(
                        "usage_recording_rollback_failed",
                        tenant_id=str(tenant_id),
                        error=str(rollback_exc),
                    )
            # Don't fail the request if we can't record usage
            # (the usage is what matters, not the audit log)
        finally:
            await cls._release_fair_use_inflight_slot(tenant_id)

    @classmethod
    async def check_budget(cls, tenant_id: UUID, db: AsyncSession) -> BudgetStatus:
        """
        Unified budget check for tenants.
        Returns: OK, SOFT_LIMIT, or HARD_LIMIT (via exception).
        """

        # 1. Cache Check
        cache = get_cache_service()
        if cache.enabled and cache.client is not None:
            try:
                if await cache.client.get(f"budget_blocked:{tenant_id}"):
                    return BudgetStatus.HARD_LIMIT
                if await cache.client.get(f"budget_soft:{tenant_id}"):
                    return BudgetStatus.SOFT_LIMIT
            except Exception as e:
                # Fail-Closed: If budget state is unknown due to infrastructure failure,
                # we must deny the request to prevent uncontrolled costs.
                logger.error(
                    "llm_budget_check_cache_error_fail_closed",
                    error=str(e),
                    tenant_id=str(tenant_id),
                )
                raise BudgetExceededError(
                    "Fail-Closed: LLM Budget check failed due to system error.",
                    details={"error": "service_unavailable", "reason": str(e)},
                )

        # 2. DB Check
        result = await db.execute(
            select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
        )
        budget = result.scalar_one_or_none()
        if not budget:
            return BudgetStatus.OK

        limit = cls._to_decimal(budget.monthly_limit_usd)
        current_usage = budget.monthly_spend_usd + budget.pending_reservations_usd
        threshold = cls._to_decimal(budget.alert_threshold_percent) / Decimal("100")

        if current_usage >= limit:
            if budget.hard_limit:
                if cache.enabled and cache.client is not None:
                    await cache.client.set(f"budget_blocked:{tenant_id}", "1", ex=600)
                raise BudgetExceededError(
                    f"LLM budget of ${limit:.2f} exceeded.",
                    details={"usage": float(current_usage), "limit": float(limit)},
                )
            return BudgetStatus.SOFT_LIMIT

        if current_usage >= (limit * threshold):
            if cache.enabled and cache.client is not None:
                await cache.client.set(f"budget_soft:{tenant_id}", "1", ex=300)
            return BudgetStatus.SOFT_LIMIT

        return BudgetStatus.OK

    @classmethod
    async def _check_budget_and_alert(
        cls, tenant_id: UUID, db: AsyncSession, last_cost: Decimal
    ) -> None:
        """
        Checks budget threshold and sends Slack alerts if needed.
        """
        result = await db.execute(
            select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
        )
        budget = result.scalar_one_or_none()
        if not budget:
            return

        # Simplified usage check for alerting (could use cached value or sum)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result_usage = await db.execute(
            select(func.coalesce(func.sum(LLMUsage.cost_usd), Decimal("0"))).where(
                (LLMUsage.tenant_id == tenant_id) & (LLMUsage.created_at >= month_start)
            )
        )
        current_usage = cls._to_decimal(result_usage.scalar())

        limit = cls._to_decimal(budget.monthly_limit_usd)
        threshold_percent = cls._to_decimal(budget.alert_threshold_percent)
        usage_percent = (current_usage / limit * 100) if limit > 0 else Decimal("0")

        # Threshold check
        already_sent = (
            budget.alert_sent_at
            and budget.alert_sent_at.year == now.year
            and budget.alert_sent_at.month == now.month
        )

        if usage_percent >= threshold_percent and not already_sent:
            audit_log(
                event="llm_budget_alert",
                user_id="system",
                tenant_id=str(tenant_id),
                details={
                    "usage_usd": float(current_usage),
                    "limit_usd": float(limit),
                    "percent": float(usage_percent),
                },
            )

            try:
                from app.modules.notifications.domain import get_tenant_slack_service

                slack = await get_tenant_slack_service(db, tenant_id)
                if slack:
                    await slack.send_alert(
                        title="LLM Budget Alert",
                        message=f"Usage: ${current_usage:.2f} / ${limit:.2f} ({usage_percent:.1f}%)",
                        severity="critical" if usage_percent >= 100 else "warning",
                    )
                else:
                    logger.info(
                        "llm_budget_alert_slack_not_configured",
                        tenant_id=str(tenant_id),
                    )
            except Exception as exc:
                logger.warning(
                    "llm_budget_alert_slack_dispatch_failed",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )

            budget.alert_sent_at = now
            await db.flush()
            await db.commit()
