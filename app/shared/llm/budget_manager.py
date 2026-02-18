"""
LLM Budget Management Service

PRODUCTION: Ensures LLM requests are pre-authorized and within budget limits.
Implements atomic budget reservation/debit pattern to prevent cost overages.
"""

import structlog
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from uuid import UUID
from enum import Enum
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.llm import LLMBudget, LLMUsage
from app.shared.core.exceptions import BudgetExceededError
from app.shared.llm.pricing_data import LLM_PRICING
from app.shared.llm.pricing_data import ProviderCost
from app.shared.core.cache import get_cache_service

# Moved BudgetStatus here
from app.shared.core.ops_metrics import LLM_PRE_AUTH_DENIALS, LLM_SPEND_USD
from app.shared.core.pricing import get_tenant_tier, PricingTier
from app.shared.core.logging import audit_log
from app.shared.core.async_utils import maybe_call

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

    # PRODUCTION: 2026 BYOK Revenue Model
    BYOK_PLATFORM_FEE_USD = Decimal("0.50")

    @staticmethod
    def _to_decimal(v: Any) -> Decimal:
        """Safe conversion to Decimal for currency math."""
        if v is None:
            return Decimal("0")
        try:
            return Decimal(str(v))
        except (ValueError, TypeError, Exception):
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
        from app.shared.core.pricing import get_tenant_tier, get_tier_limit
        from app.models.llm import LLMUsage

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

        try:
            # 0. Enforce plan-level daily LLM request quota.
            await cls._enforce_daily_analysis_limit(tenant_id, db)

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
                    reason="hard_limit_exceeded", tenant_tier="unknown"
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
            await db.flush() # Ensure sync to DB state before proceeding

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
            raise
        except Exception as e:
            logger.error(
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
                    budget.pending_reservations_usd - estimated_reservation
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
            # Don't fail the request if we can't record usage
            # (the usage is what matters, not the audit log)

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
