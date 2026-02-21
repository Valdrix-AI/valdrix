from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.llm.budget_fair_use import (
    enforce_fair_use_guards,
)

if TYPE_CHECKING:
    from app.shared.llm.budget_manager import BudgetStatus


def _coerce_decimal(value: Any) -> Decimal | None:
    """Return Decimal for supported scalar types, otherwise None."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_threshold_percent(value: Any) -> Decimal:
    threshold = _coerce_decimal(value)
    if threshold is None:
        return Decimal("80")
    if threshold < 0:
        return Decimal("0")
    if threshold > 100:
        return Decimal("100")
    return threshold


async def check_and_reserve_budget(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    prompt_tokens: int,
    completion_tokens: int,
    operation_id: str | None = None,
) -> Decimal:
    """
    Check budget and atomically reserve funds.
    """
    import app.shared.llm.budget_manager as manager_module

    estimated_cost = cast(
        Decimal,
        manager_cls.estimate_cost(
            prompt_tokens, completion_tokens, model, provider
        ),
    )
    concurrency_slot_acquired = False
    tier_for_metrics = "unknown"

    try:
        await manager_cls._enforce_daily_analysis_limit(tenant_id, db)
        if manager_module.get_settings().LLM_FAIR_USE_GUARDS_ENABLED:
            tier = await manager_module.get_tenant_tier(tenant_id, db)
            tier_for_metrics = tier.value
            concurrency_slot_acquired = await enforce_fair_use_guards(
                manager_cls=manager_cls,
                tenant_id=tenant_id,
                db=db,
                tier=tier,
            )

        result = await db.execute(
            select(manager_module.LLMBudget)
            .where(manager_module.LLMBudget.tenant_id == tenant_id)
            .with_for_update()
        )
        budget = result.scalar_one_or_none()

        if not budget:
            tier = await manager_module.get_tenant_tier(tenant_id, db)
            default_limit = Decimal("1.00")
            if tier in {
                manager_module.PricingTier.STARTER,
                manager_module.PricingTier.GROWTH,
            }:
                default_limit = Decimal("10.00")
            elif tier in {
                manager_module.PricingTier.PRO,
                manager_module.PricingTier.ENTERPRISE,
            }:
                default_limit = Decimal("50.00")

            budget = manager_module.LLMBudget(
                tenant_id=tenant_id,
                monthly_limit_usd=float(default_limit),
                alert_threshold_percent=80,
                hard_limit=True,
                preferred_provider="groq",
                preferred_model="llama-3.3-70b-versatile",
            )
            db.add(budget)
            await db.flush()
            manager_module.logger.info(
                "budget_auto_bootstrapped",
                tenant_id=str(tenant_id),
                tier=tier.value,
                monthly_limit_usd=float(default_limit),
            )

        now = datetime.now(timezone.utc)
        if (
            budget.budget_reset_at.year != now.year
            or budget.budget_reset_at.month != now.month
        ):
            manager_module.logger.info(
                "llm_budget_month_reset",
                tenant_id=str(tenant_id),
                old_reset=budget.budget_reset_at.isoformat(),
                new_reset=now.isoformat(),
                previous_spend=float(budget.monthly_spend_usd),
            )
            budget.monthly_spend_usd = Decimal("0.0")
            budget.pending_reservations_usd = Decimal("0.0")
            budget.budget_reset_at = now

        limit = manager_cls._to_decimal(budget.monthly_limit_usd)
        current_total = budget.monthly_spend_usd + budget.pending_reservations_usd
        remaining_budget = limit - current_total

        if estimated_cost > remaining_budget:
            manager_module.logger.warning(
                "llm_budget_exceeded",
                tenant_id=str(tenant_id),
                model=model,
                estimated_cost=float(estimated_cost),
                remaining_budget=float(remaining_budget),
                monthly_limit=float(limit),
                current_total_committed=float(current_total),
            )

            manager_module.LLM_PRE_AUTH_DENIALS.labels(
                reason="hard_limit_exceeded", tenant_tier=tier_for_metrics
            ).inc()

            raise manager_module.BudgetExceededError(
                f"LLM budget exceeded. Required: ${float(estimated_cost):.4f}, Available: ${float(remaining_budget):.4f}",
                details={
                    "monthly_limit": float(limit),
                    "current_total_committed": float(current_total),
                    "estimated_cost": float(estimated_cost),
                    "remaining_budget": float(remaining_budget),
                    "model": model,
                },
            )

        budget.pending_reservations_usd += estimated_cost
        await db.flush()

        manager_module.logger.info(
            "llm_budget_reserved",
            tenant_id=str(tenant_id),
            model=model,
            reserved_amount=float(estimated_cost),
            new_pending_total=float(budget.pending_reservations_usd),
            operation_id=operation_id,
        )

        return estimated_cost

    except manager_module.BudgetExceededError:
        if concurrency_slot_acquired:
            await manager_cls._release_fair_use_inflight_slot(tenant_id)
        raise
    except Exception as exc:
        if concurrency_slot_acquired:
            await manager_cls._release_fair_use_inflight_slot(tenant_id)
        manager_module.logger.exception(
            "budget_check_failed",
            tenant_id=str(tenant_id),
            model=model,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


async def record_usage_entry(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    *,
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
    import app.shared.llm.budget_manager as manager_module

    try:
        result = await db.execute(
            select(manager_module.LLMBudget)
            .where(manager_module.LLMBudget.tenant_id == tenant_id)
            .with_for_update()
        )
        budget_accessor = getattr(result, "scalar_one_or_none", None)
        budget_candidate: Any = None
        if callable(budget_accessor):
            budget_candidate = budget_accessor()
            if inspect.isawaitable(budget_candidate):
                budget_candidate = await budget_candidate
        budget = budget_candidate

        if is_byok:
            actual_cost_usd = manager_cls.BYOK_PLATFORM_FEE_USD
        elif actual_cost_usd is None:
            actual_cost_usd = manager_cls.estimate_cost(
                prompt_tokens, completion_tokens, model, provider
            )

        actual_cost_decimal = manager_cls._to_decimal(actual_cost_usd)

        if budget:
            estimated_reservation = manager_cls.estimate_cost(
                prompt_tokens, completion_tokens, model, provider
            )
            pending_raw = getattr(budget, "pending_reservations_usd", Decimal("0"))
            spend_raw = getattr(budget, "monthly_spend_usd", Decimal("0"))
            pending = _coerce_decimal(pending_raw)
            spend = _coerce_decimal(spend_raw)

            if pending is not None and spend is not None:
                budget.pending_reservations_usd = max(
                    Decimal("0.0"),
                    pending - estimated_reservation,
                )
                budget.monthly_spend_usd = spend + actual_cost_decimal
                await db.flush()

        usage = manager_module.LLMUsage(
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

        try:
            tier = await manager_module.get_tenant_tier(tenant_id, db)
            manager_module.LLM_SPEND_USD.labels(
                tenant_tier=tier.value, provider=provider, model=model
            ).inc(float(actual_cost_usd))
        except Exception as exc:
            manager_module.logger.debug(
                "llm_spend_metric_inc_failed", error=str(exc), exc_info=True
            )

        await db.flush()
        await db.commit()

        await manager_cls._check_budget_and_alert(tenant_id, db, actual_cost_usd)

        manager_module.logger.info(
            "llm_usage_recorded",
            tenant_id=str(tenant_id),
            model=model,
            tokens_total=prompt_tokens + completion_tokens,
            cost=float(actual_cost_usd),
            operation_id=operation_id,
        )

    except Exception as exc:
        manager_module.logger.error(
            "usage_recording_failed",
            tenant_id=str(tenant_id),
            model=model,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        rollback_fn = getattr(db, "rollback", None)
        if callable(rollback_fn):
            try:
                rollback_result = rollback_fn()
                if inspect.isawaitable(rollback_result):
                    await rollback_result
            except Exception as rollback_exc:
                manager_module.logger.warning(
                    "usage_recording_rollback_failed",
                    tenant_id=str(tenant_id),
                    error=str(rollback_exc),
                )
    finally:
        await manager_cls._release_fair_use_inflight_slot(tenant_id)


async def check_budget_state(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
) -> BudgetStatus:
    """
    Unified budget check for tenants.
    Returns: OK, SOFT_LIMIT, or HARD_LIMIT (via exception).
    """
    import app.shared.llm.budget_manager as manager_module

    cache = manager_module.get_cache_service()
    if cache.enabled and cache.client is not None:
        try:
            if await cache.client.get(f"budget_blocked:{tenant_id}"):
                return manager_module.BudgetStatus.HARD_LIMIT
            if await cache.client.get(f"budget_soft:{tenant_id}"):
                return manager_module.BudgetStatus.SOFT_LIMIT
        except Exception as exc:
            manager_module.logger.error(
                "llm_budget_check_cache_error_fail_closed",
                error=str(exc),
                tenant_id=str(tenant_id),
            )
            raise manager_module.BudgetExceededError(
                "Fail-Closed: LLM Budget check failed due to system error.",
                details={"error": "service_unavailable", "reason": str(exc)},
            )

    result = await db.execute(
        select(manager_module.LLMBudget).where(
            manager_module.LLMBudget.tenant_id == tenant_id
        )
    )
    budget_accessor = getattr(result, "scalar_one_or_none", None)
    budget: Any = None
    if callable(budget_accessor):
        budget = budget_accessor()
        if inspect.isawaitable(budget):
            budget = await budget
    if not budget:
        return manager_module.BudgetStatus.OK

    limit_raw = getattr(budget, "monthly_limit_usd", None)
    spend_raw = getattr(budget, "monthly_spend_usd", Decimal("0"))
    pending_raw = getattr(budget, "pending_reservations_usd", Decimal("0"))
    limit_dec = _coerce_decimal(limit_raw)
    spend_dec = _coerce_decimal(spend_raw)
    pending_dec = _coerce_decimal(pending_raw)
    if limit_dec is None or spend_dec is None or pending_dec is None:
        return manager_module.BudgetStatus.OK

    limit = manager_cls._to_decimal(limit_dec)
    current_usage = manager_cls._to_decimal(spend_dec) + manager_cls._to_decimal(
        pending_dec
    )
    threshold = _coerce_threshold_percent(
        getattr(budget, "alert_threshold_percent", Decimal("80"))
    ) / Decimal("100")
    hard_limit = _coerce_bool(getattr(budget, "hard_limit", False), default=False)

    if current_usage >= limit:
        if hard_limit:
            if cache.enabled and cache.client is not None:
                await cache.client.set(f"budget_blocked:{tenant_id}", "1", ex=600)
            raise manager_module.BudgetExceededError(
                f"LLM budget of ${limit:.2f} exceeded.",
                details={"usage": float(current_usage), "limit": float(limit)},
            )
        return manager_module.BudgetStatus.SOFT_LIMIT

    if current_usage >= (limit * threshold):
        if cache.enabled and cache.client is not None:
            await cache.client.set(f"budget_soft:{tenant_id}", "1", ex=300)
        return manager_module.BudgetStatus.SOFT_LIMIT

    return manager_module.BudgetStatus.OK


async def check_budget_and_alert(
    manager_cls: Any,
    tenant_id: UUID,
    db: AsyncSession,
    last_cost: Decimal,
) -> None:
    """
    Checks budget threshold and sends Slack alerts if needed.
    """
    import app.shared.llm.budget_manager as manager_module

    result = await db.execute(
        select(manager_module.LLMBudget).where(
            manager_module.LLMBudget.tenant_id == tenant_id
        )
    )
    budget = result.scalar_one_or_none()
    if inspect.isawaitable(budget):
        budget = await budget
    if not budget:
        return

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result_usage = await db.execute(
        select(func.coalesce(func.sum(manager_module.LLMUsage.cost_usd), Decimal("0"))).where(
            (manager_module.LLMUsage.tenant_id == tenant_id)
            & (manager_module.LLMUsage.created_at >= month_start)
        )
    )
    current_usage = manager_cls._to_decimal(result_usage.scalar())

    limit_raw = getattr(budget, "monthly_limit_usd", None)
    threshold_raw = getattr(budget, "alert_threshold_percent", Decimal("80"))
    limit_dec = _coerce_decimal(limit_raw)
    if limit_dec is None:
        return
    limit = manager_cls._to_decimal(limit_dec)
    threshold_percent = _coerce_threshold_percent(threshold_raw)
    usage_percent = (current_usage / limit * 100) if limit > 0 else Decimal("0")

    alert_sent_at = getattr(budget, "alert_sent_at", None)
    already_sent = (
        isinstance(alert_sent_at, datetime)
        and alert_sent_at.year == now.year
        and alert_sent_at.month == now.month
    )

    if usage_percent >= threshold_percent and not already_sent:
        manager_module.audit_log(
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
                manager_module.logger.info(
                    "llm_budget_alert_slack_not_configured",
                    tenant_id=str(tenant_id),
                )
        except Exception as exc:
            manager_module.logger.warning(
                "llm_budget_alert_slack_dispatch_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )

        budget.alert_sent_at = now
        await db.flush()
        await db.commit()
