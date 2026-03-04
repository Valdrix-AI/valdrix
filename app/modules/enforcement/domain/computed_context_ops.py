from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Awaitable, Callable, cast
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CostRecord
from app.models.enforcement import EnforcementPolicy
from app.modules.enforcement.domain.service_models import DecisionComputedContext
from app.modules.enforcement.domain.service_utils import _as_utc, _quantize, _to_decimal
from app.shared.core.pricing import PricingTier, get_tenant_tier, get_tier_limit


logger = structlog.get_logger()


async def resolve_tenant_tier(
    *,
    tenant_id: UUID,
    db: AsyncSession,
    get_tenant_tier_fn: Callable[[UUID, AsyncSession], Any],
) -> PricingTier:
    tier = await get_tenant_tier_fn(tenant_id, db)
    return tier if isinstance(tier, PricingTier) else PricingTier.FREE


async def resolve_plan_monthly_ceiling_usd(
    *,
    policy: EnforcementPolicy,
    tenant_tier: PricingTier,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
    get_tier_limit_fn: Callable[[PricingTier, str], Any],
) -> Decimal | None:
    configured = policy.plan_monthly_ceiling_usd
    if configured is not None:
        normalized = quantize_fn(to_decimal_fn(configured), "0.0001")
        return normalized if normalized > Decimal("0.0000") else None

    raw = get_tier_limit_fn(tenant_tier, "enforcement_plan_monthly_ceiling_usd")
    if raw is None:
        return None
    ceiling = quantize_fn(to_decimal_fn(raw), "0.0001")
    if ceiling <= Decimal("0.0000"):
        return None
    return ceiling


async def resolve_enterprise_monthly_ceiling_usd(
    *,
    policy: EnforcementPolicy,
    tenant_tier: PricingTier,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
    get_tier_limit_fn: Callable[[PricingTier, str], Any],
) -> Decimal | None:
    configured = policy.enterprise_monthly_ceiling_usd
    if configured is not None:
        normalized = quantize_fn(to_decimal_fn(configured), "0.0001")
        return normalized if normalized > Decimal("0.0000") else None

    raw = get_tier_limit_fn(tenant_tier, "enforcement_enterprise_monthly_ceiling_usd")
    if raw is None:
        return None
    ceiling = quantize_fn(to_decimal_fn(raw), "0.0001")
    if ceiling <= Decimal("0.0000"):
        return None
    return ceiling


def month_total_days(value: date) -> int:
    return int(calendar.monthrange(value.year, value.month)[1])


async def load_daily_cost_totals(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    final_only: bool,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
) -> dict[date, Decimal]:
    stmt = (
        select(
            CostRecord.recorded_at.label("recorded_at"),
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("total_cost_usd"),
        )
        .where(CostRecord.tenant_id == tenant_id)
        .where(CostRecord.recorded_at >= start_date)
        .where(CostRecord.recorded_at <= end_date)
        .group_by(CostRecord.recorded_at)
    )
    if final_only:
        stmt = stmt.where(CostRecord.cost_status == "FINAL")

    rows = await db.execute(stmt)
    return {
        cast(date, item.recorded_at): quantize_fn(
            to_decimal_fn(item.total_cost_usd),
            "0.0001",
        )
        for item in rows.all()
    }


def derive_risk_assessment(
    *,
    gate_input: Any,
    is_production: bool,
    anomaly_signal: bool,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
) -> tuple[str, int, tuple[str, ...]]:
    metadata = gate_input.metadata if isinstance(gate_input.metadata, dict) else {}
    action = str(gate_input.action or "").strip().lower()
    resource_reference = str(gate_input.resource_reference or "").strip().lower()
    resource_type = str(metadata.get("resource_type") or "").strip().lower()
    resource_class = str(metadata.get("resource_class") or resource_type).strip().lower()
    criticality = (
        str(
            metadata.get("criticality")
            or metadata.get("business_criticality")
            or metadata.get("service_criticality")
            or ""
        )
        .strip()
        .lower()
    )
    monthly_delta = quantize_fn(to_decimal_fn(gate_input.estimated_monthly_delta_usd), "0.0001")

    score = 0
    factors: list[str] = []

    if is_production:
        score += 3
        factors.append("production_environment")

    destructive_markers = (
        "destroy",
        "delete",
        "terminate",
        "remove",
        "revoke",
        "detach",
        "scale_down",
        "downscale",
    )
    if any(marker in action for marker in destructive_markers):
        score += 2
        factors.append("destructive_action")

    high_criticality_values = {"critical", "high", "tier0", "tier1", "p0", "sev0"}
    medium_criticality_values = {"medium", "tier2", "p1", "sev1"}
    if criticality in high_criticality_values:
        score += 2
        factors.append("criticality_high")
    elif criticality in medium_criticality_values:
        score += 1
        factors.append("criticality_medium")

    high_impact_markers = (
        "gpu",
        "db",
        "database",
        "cluster",
        "k8s",
        "kubernetes",
        "warehouse",
        "redshift",
        "bigquery",
        "rds",
        "postgres",
        "mysql",
        "elasticsearch",
    )
    impact_text = " ".join([resource_class, resource_type, resource_reference])
    if any(marker in impact_text for marker in high_impact_markers):
        score += 1
        factors.append("high_impact_resource_class")

    if monthly_delta >= Decimal("5000.0000"):
        score += 2
        factors.append("large_monthly_delta")
    elif monthly_delta >= Decimal("1000.0000"):
        score += 1
        factors.append("moderate_monthly_delta")

    if anomaly_signal:
        score += 1
        factors.append("anomaly_spike_signal")

    if score >= 6:
        risk_class = "high"
    elif score >= 3:
        risk_class = "medium"
    else:
        risk_class = "low"

    return risk_class, score, tuple(factors)


async def build_decision_computed_context_payload(
    *,
    tenant_id: UUID,
    policy_version: int,
    gate_input: Any,
    now: datetime,
    is_production: bool,
    as_utc_fn: Callable[[datetime], datetime],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
    load_daily_cost_totals_fn: Callable[
        ...,
        Awaitable[dict[date, Decimal]],
    ],
    warning_logger_fn: Callable[..., Any],
) -> dict[str, Any]:
    context_version = "enforcement_computed_context_v1"
    now_utc = as_utc_fn(now)
    today = now_utc.date()
    month_start = today.replace(day=1)
    month_total = month_total_days(today)
    month_end = today.replace(day=month_total)
    month_elapsed_days = max(1, (today - month_start).days + 1)

    lookback_start = today - timedelta(days=35)
    data_source_mode = "final"
    latest_cost_date: date | None = None
    mtd_spend_usd = Decimal("0.0000")
    observed_cost_days = 0
    burn_rate_daily_usd = Decimal("0.0000")
    forecast_eom_usd = Decimal("0.0000")
    anomaly_signal = False
    anomaly_kind: str | None = None
    anomaly_delta_usd = Decimal("0.0000")
    anomaly_percent: Decimal | None = None
    daily_totals: dict[date, Decimal] = {}

    try:
        daily_totals = await load_daily_cost_totals_fn(
            tenant_id=tenant_id,
            start_date=lookback_start,
            end_date=today,
            final_only=True,
        )
        if not daily_totals:
            daily_totals = await load_daily_cost_totals_fn(
                tenant_id=tenant_id,
                start_date=lookback_start,
                end_date=today,
                final_only=False,
            )
            data_source_mode = "all_status" if daily_totals else "none"
    except (
        SQLAlchemyError,
        ArithmeticError,
        ValueError,
        TypeError,
        RuntimeError,
    ) as exc:
        data_source_mode = "unavailable"
        warning_logger_fn(
            "enforcement_computed_context_unavailable",
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
        )

    if daily_totals:
        latest_cost_date = max(daily_totals.keys())
        mtd_spend_usd = quantize_fn(
            sum(
                (
                    amount
                    for day, amount in daily_totals.items()
                    if month_start <= day <= today
                ),
                Decimal("0.0000"),
            ),
            "0.0001",
        )
        observed_cost_days = sum(
            1
            for day, amount in daily_totals.items()
            if month_start <= day <= today and amount > Decimal("0.0000")
        )
        burn_rate_daily_usd = quantize_fn(
            mtd_spend_usd / Decimal(month_elapsed_days),
            "0.0001",
        )
        forecast_eom_usd = quantize_fn(
            burn_rate_daily_usd * Decimal(month_total),
            "0.0001",
        )

        today_total = quantize_fn(
            to_decimal_fn(daily_totals.get(today, Decimal("0.0000"))),
            "0.0001",
        )
        baseline_days = [today - timedelta(days=offset) for offset in range(1, 8)]
        baseline_total = quantize_fn(
            sum(
                (
                    to_decimal_fn(daily_totals.get(day, Decimal("0.0000")))
                    for day in baseline_days
                ),
                Decimal("0.0000"),
            ),
            "0.0001",
        )
        baseline_avg = quantize_fn(
            baseline_total / Decimal("7"),
            "0.0001",
        )

        anomaly_delta_usd = quantize_fn(today_total - baseline_avg, "0.0001")
        if baseline_avg > Decimal("0.0000"):
            anomaly_percent = quantize_fn(
                (anomaly_delta_usd / baseline_avg) * Decimal("100"),
                "0.01",
            )

        if baseline_avg <= Decimal("0.0000") and today_total >= Decimal("100.0000"):
            anomaly_signal = True
            anomaly_kind = "new_spend"
        elif (
            anomaly_delta_usd >= Decimal("100.0000")
            and anomaly_percent is not None
            and anomaly_percent >= Decimal("30.00")
        ):
            anomaly_signal = True
            anomaly_kind = "spike"

    risk_class, risk_score, risk_factors = derive_risk_assessment(
        gate_input=gate_input,
        is_production=is_production,
        anomaly_signal=anomaly_signal,
        quantize_fn=quantize_fn,
        to_decimal_fn=to_decimal_fn,
    )

    return {
        "context_version": context_version,
        "generated_at": now_utc,
        "policy_version": int(policy_version),
        "month_start": month_start,
        "month_end": month_end,
        "month_elapsed_days": month_elapsed_days,
        "month_total_days": month_total,
        "observed_cost_days": observed_cost_days,
        "latest_cost_date": latest_cost_date,
        "mtd_spend_usd": mtd_spend_usd,
        "burn_rate_daily_usd": burn_rate_daily_usd,
        "forecast_eom_usd": forecast_eom_usd,
        "anomaly_signal": anomaly_signal,
        "anomaly_kind": anomaly_kind,
        "anomaly_delta_usd": anomaly_delta_usd,
        "anomaly_percent": anomaly_percent,
        "data_source_mode": data_source_mode,
        "risk_class": risk_class,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
    }


async def resolve_tenant_tier_for_service(service: Any, tenant_id: UUID) -> PricingTier:
    from app.modules.enforcement.domain import service as enforcement_service_module

    return await resolve_tenant_tier(
        tenant_id=tenant_id,
        db=service.db,
        get_tenant_tier_fn=getattr(
            enforcement_service_module,
            "get_tenant_tier",
            get_tenant_tier,
        ),
    )


async def resolve_plan_monthly_ceiling_usd_for_service(
    service: Any,
    *,
    policy: EnforcementPolicy,
    tenant_tier: PricingTier,
) -> Decimal | None:
    from app.modules.enforcement.domain import service as enforcement_service_module

    return await resolve_plan_monthly_ceiling_usd(
        policy=policy,
        tenant_tier=tenant_tier,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
        get_tier_limit_fn=getattr(
            enforcement_service_module,
            "get_tier_limit",
            get_tier_limit,
        ),
    )


async def resolve_enterprise_monthly_ceiling_usd_for_service(
    service: Any,
    *,
    policy: EnforcementPolicy,
    tenant_tier: PricingTier,
) -> Decimal | None:
    from app.modules.enforcement.domain import service as enforcement_service_module

    return await resolve_enterprise_monthly_ceiling_usd(
        policy=policy,
        tenant_tier=tenant_tier,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
        get_tier_limit_fn=getattr(
            enforcement_service_module,
            "get_tier_limit",
            get_tier_limit,
        ),
    )


def month_total_days_for_service(_service: Any, value: date) -> int:
    return month_total_days(value)


async def load_daily_cost_totals_for_service(
    service: Any,
    *,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    final_only: bool,
) -> dict[date, Decimal]:
    return await load_daily_cost_totals(
        db=service.db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        final_only=final_only,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
    )


def derive_risk_assessment_for_service(
    _service: Any,
    *,
    gate_input: Any,
    is_production: bool,
    anomaly_signal: bool,
) -> tuple[str, int, tuple[str, ...]]:
    return derive_risk_assessment(
        gate_input=gate_input,
        is_production=is_production,
        anomaly_signal=anomaly_signal,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
    )


async def build_decision_computed_context_for_service(
    service: Any,
    *,
    tenant_id: UUID,
    policy_version: int,
    gate_input: Any,
    now: datetime,
    is_production: bool,
) -> DecisionComputedContext:
    from app.modules.enforcement.domain import service as enforcement_service_module

    warning_logger = getattr(
        getattr(enforcement_service_module, "logger", logger),
        "warning",
        logger.warning,
    )
    payload = await build_decision_computed_context_payload(
        tenant_id=tenant_id,
        policy_version=policy_version,
        gate_input=gate_input,
        now=now,
        is_production=is_production,
        as_utc_fn=_as_utc,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
        load_daily_cost_totals_fn=service._load_daily_cost_totals,
        warning_logger_fn=warning_logger,
    )
    return DecisionComputedContext(**payload)
