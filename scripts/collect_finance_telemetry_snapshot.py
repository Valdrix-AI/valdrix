#!/usr/bin/env python3
"""Collect monthly finance telemetry snapshot for FIN packet generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.pricing import PricingTier, TIER_CONFIG
from app.shared.db.session import async_session_maker

TRACKED_TIERS: tuple[str, ...] = ("free", "starter", "growth", "pro", "enterprise")
ACTIVE_SUBSCRIPTION_STATUSES: tuple[str, ...] = (
    "active",
    "non-renewing",
    "attention",
    "trial",
)
FREE_TIER_GUARDRAIL_LIMIT_KEYS: tuple[str, ...] = (
    "llm_analyses_per_day",
    "llm_analyses_per_user_per_day",
    "llm_system_analyses_per_day",
    "llm_analysis_max_records",
    "llm_analysis_max_window_days",
    "llm_prompt_max_input_tokens",
    "llm_output_max_tokens",
)
FREE_TIER_MAX_COST_PCT_OF_STARTER_MRR = 100.0


def _parse_date(value: str, *, field: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _window_bounds(
    start_date: date,
    end_date: date,
) -> tuple[datetime, datetime]:
    if end_date < start_date:
        raise ValueError("end date must be >= start date")
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    # Exclusive upper bound for robust range predicates.
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_dt, end_dt


def _default_window() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    first_of_month = today.replace(day=1)
    end_date = first_of_month - timedelta(days=1)
    start_date = end_date.replace(day=1)
    return start_date, end_date


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0.0)


def _to_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if percentile <= 0.0:
        return float(min(values))
    if percentile >= 100.0:
        return float(max(values))
    ordered = sorted(float(v) for v in values)
    rank = ((percentile / 100.0) * (len(ordered) - 1))
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _monthly_price_usd(tier: str) -> float:
    config = TIER_CONFIG[PricingTier(tier)]
    price = config.get("price_usd")
    if isinstance(price, dict):
        return float(price.get("monthly", 0.0))
    return float(price or 0.0)


def _annual_price_usd(tier: str) -> float:
    config = TIER_CONFIG[PricingTier(tier)]
    price = config.get("price_usd")
    if isinstance(price, dict):
        annual = price.get("annual")
        return float(annual or 0.0)
    # For zero-priced/free tiers annual is equivalent.
    return float(price or 0.0) * 12.0


def _build_pricing_reference() -> dict[str, dict[str, float]]:
    reference: dict[str, dict[str, float]] = {}
    for tier in TRACKED_TIERS:
        monthly = _monthly_price_usd(tier)
        annual = _annual_price_usd(tier)
        annual_factor = 0.0
        if monthly > 0.0 and annual > 0.0:
            annual_factor = annual / (monthly * 12.0)
        reference[tier] = {
            "monthly_price_usd": round(monthly, 4),
            "annual_price_usd": round(annual, 4),
            "annual_monthly_factor": round(annual_factor, 6),
        }
    return reference


def _build_free_tier_compute_guardrails() -> dict[str, Any]:
    free_limits = TIER_CONFIG[PricingTier.FREE].get("limits", {})
    starter_limits = TIER_CONFIG[PricingTier.STARTER].get("limits", {})
    rows: list[dict[str, Any]] = []
    bounded = True
    for limit_name in FREE_TIER_GUARDRAIL_LIMIT_KEYS:
        free_limit = _to_non_negative_int(free_limits.get(limit_name))
        starter_limit = _to_non_negative_int(starter_limits.get(limit_name))
        free_le_starter = free_limit <= starter_limit
        bounded = bounded and free_le_starter
        rows.append(
            {
                "limit_name": limit_name,
                "free_limit": free_limit,
                "starter_limit": starter_limit,
                "free_le_starter": free_le_starter,
            }
        )
    return {
        "tier": "free",
        "reference_tier": "starter",
        "limits": rows,
        "bounded_against_starter": bounded,
    }


async def _fetch_subscription_snapshot(
    db: AsyncSession,
    *,
    window_start: datetime,
    window_end_exclusive: datetime,
) -> dict[str, dict[str, int]]:
    query = text(
        """
        WITH effective_tiers AS (
            SELECT
                t.id AS tenant_id,
                LOWER(COALESCE(NULLIF(ts.tier, ''), NULLIF(t.plan, ''), 'free')) AS tier,
                LOWER(COALESCE(ts.status, 'active')) AS subscription_status,
                ts.last_dunning_at AS last_dunning_at
            FROM tenants t
            LEFT JOIN tenant_subscriptions ts ON ts.tenant_id = t.id
            WHERE COALESCE(t.is_deleted, FALSE) = FALSE
        )
        SELECT
            tier,
            COUNT(*) AS total_tenants,
            SUM(
                CASE
                    WHEN subscription_status IN :active_statuses THEN 1
                    ELSE 0
                END
            ) AS active_subscriptions,
            SUM(
                CASE
                    WHEN last_dunning_at IS NOT NULL
                         AND last_dunning_at >= :window_start
                         AND last_dunning_at < :window_end_exclusive
                    THEN 1
                    ELSE 0
                END
            ) AS dunning_events
        FROM effective_tiers
        GROUP BY tier
        """
    ).bindparams(active_statuses=ACTIVE_SUBSCRIPTION_STATUSES, expanding=True)
    result = await db.execute(
        query,
        {
            "window_start": window_start,
            "window_end_exclusive": window_end_exclusive,
        },
    )
    rows = result.fetchall()

    snapshot: dict[str, dict[str, int]] = {
        tier: {"total_tenants": 0, "active_subscriptions": 0, "dunning_events": 0}
        for tier in TRACKED_TIERS
    }
    for row in rows:
        tier = str(row.tier or "").strip().lower()
        if tier not in snapshot:
            continue
        snapshot[tier] = {
            "total_tenants": int(row.total_tenants or 0),
            "active_subscriptions": int(row.active_subscriptions or 0),
            "dunning_events": int(row.dunning_events or 0),
        }
    return snapshot


async def _fetch_llm_usage_snapshot(
    db: AsyncSession,
    *,
    window_start: datetime,
    window_end_exclusive: datetime,
) -> dict[str, dict[str, float]]:
    query = text(
        """
        WITH effective_tiers AS (
            SELECT
                t.id AS tenant_id,
                LOWER(COALESCE(NULLIF(ts.tier, ''), NULLIF(t.plan, ''), 'free')) AS tier
            FROM tenants t
            LEFT JOIN tenant_subscriptions ts ON ts.tenant_id = t.id
            WHERE COALESCE(t.is_deleted, FALSE) = FALSE
        )
        SELECT
            e.tier AS tier,
            e.tenant_id AS tenant_id,
            COALESCE(SUM(lu.cost_usd), 0) AS tenant_monthly_cost_usd
        FROM effective_tiers e
        LEFT JOIN llm_usage lu
            ON lu.tenant_id = e.tenant_id
           AND lu.created_at >= :window_start
           AND lu.created_at < :window_end_exclusive
        GROUP BY e.tier, e.tenant_id
        """
    )
    result = await db.execute(
        query,
        {
            "window_start": window_start,
            "window_end_exclusive": window_end_exclusive,
        },
    )
    rows = result.fetchall()

    tier_costs: dict[str, list[float]] = {tier: [] for tier in TRACKED_TIERS}
    for row in rows:
        tier = str(row.tier or "").strip().lower()
        if tier not in tier_costs:
            continue
        tier_costs[tier].append(_to_float(row.tenant_monthly_cost_usd))

    snapshot: dict[str, dict[str, float]] = {}
    for tier in TRACKED_TIERS:
        values = tier_costs[tier]
        total_cost = sum(values)
        snapshot[tier] = {
            "total_cost_usd": round(total_cost, 6),
            "p50": round(_percentile(values, 50.0), 6),
            "p95": round(_percentile(values, 95.0), 6),
            "p99": round(_percentile(values, 99.0), 6),
        }
    return snapshot


def _build_snapshot_payload(
    *,
    window_start: datetime,
    window_end_exclusive: datetime,
    label: str,
    db_engine: str,
    subscription_snapshot: dict[str, dict[str, int]],
    llm_snapshot: dict[str, dict[str, float]],
) -> dict[str, Any]:
    pricing_reference = _build_pricing_reference()
    free_tier_guardrails = _build_free_tier_compute_guardrails()
    tier_subscription_rows: list[dict[str, Any]] = []
    tier_llm_rows: list[dict[str, Any]] = []
    tier_revenue_inputs: list[dict[str, Any]] = []

    for tier in TRACKED_TIERS:
        subscription = subscription_snapshot[tier]
        llm = llm_snapshot[tier]
        active_subscriptions = int(subscription["active_subscriptions"])
        monthly_price_usd = float(pricing_reference[tier]["monthly_price_usd"])
        gross_mrr_usd = monthly_price_usd * active_subscriptions

        tier_subscription_rows.append(
            {
                "tier": tier,
                "total_tenants": int(subscription["total_tenants"]),
                "active_subscriptions": active_subscriptions,
                "dunning_events": int(subscription["dunning_events"]),
            }
        )
        tier_llm_rows.append(
            {
                "tier": tier,
                "total_cost_usd": float(llm["total_cost_usd"]),
                "tenant_monthly_cost_percentiles_usd": {
                    "p50": float(llm["p50"]),
                    "p95": float(llm["p95"]),
                    "p99": float(llm["p99"]),
                },
            }
        )
        tier_revenue_inputs.append(
            {
                "tier": tier,
                "monthly_price_usd": monthly_price_usd,
                "active_subscriptions": active_subscriptions,
                "gross_mrr_usd": round(gross_mrr_usd, 6),
            }
        )

    revenue_by_tier = {str(row["tier"]): row for row in tier_revenue_inputs}
    free_subscription = subscription_snapshot.get(
        "free",
        {"total_tenants": 0, "active_subscriptions": 0, "dunning_events": 0},
    )
    free_llm = llm_snapshot.get(
        "free",
        {"total_cost_usd": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0},
    )
    starter_gross_mrr_usd = _to_float(
        revenue_by_tier.get("starter", {}).get("gross_mrr_usd", 0.0)
    )
    free_total_llm_cost_usd = _to_float(free_llm.get("total_cost_usd"))
    if starter_gross_mrr_usd > 0.0:
        free_cost_pct_of_starter_mrr = (
            free_total_llm_cost_usd / starter_gross_mrr_usd
        ) * 100.0
        free_tier_margin_guarded = (
            free_cost_pct_of_starter_mrr <= FREE_TIER_MAX_COST_PCT_OF_STARTER_MRR
        )
    else:
        free_cost_pct_of_starter_mrr = 0.0 if free_total_llm_cost_usd <= 0.0 else float("inf")
        free_tier_margin_guarded = free_total_llm_cost_usd <= 0.0
    free_cost_pct_payload: float | None = None
    if math.isfinite(free_cost_pct_of_starter_mrr):
        free_cost_pct_payload = round(free_cost_pct_of_starter_mrr, 6)

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": {
            "start": window_start.isoformat(),
            "end": (window_end_exclusive - timedelta(microseconds=1)).isoformat(),
            "label": label,
        },
        "runtime": {
            "database_engine": db_engine,
            "collector": "scripts/collect_finance_telemetry_snapshot.py",
        },
        "pricing_reference": pricing_reference,
        "tier_subscription_snapshot": tier_subscription_rows,
        "tier_revenue_inputs": tier_revenue_inputs,
        "tier_llm_usage": tier_llm_rows,
        "free_tier_compute_guardrails": free_tier_guardrails,
        "free_tier_margin_watch": {
            "free_total_tenants": _to_non_negative_int(free_subscription["total_tenants"]),
            "free_active_subscriptions": _to_non_negative_int(
                free_subscription["active_subscriptions"]
            ),
            "free_total_llm_cost_usd": round(free_total_llm_cost_usd, 6),
            "free_p95_tenant_monthly_cost_usd": round(_to_float(free_llm.get("p95")), 6),
            "starter_gross_mrr_usd": round(starter_gross_mrr_usd, 6),
            "free_llm_cost_pct_of_starter_gross_mrr": free_cost_pct_payload,
            "max_allowed_pct_of_starter_gross_mrr": FREE_TIER_MAX_COST_PCT_OF_STARTER_MRR,
        },
        "gate_results": {
            "telemetry_gate_required_tiers_present": True,
            "telemetry_gate_window_valid": True,
            "telemetry_gate_percentiles_valid": True,
            "telemetry_gate_artifact_fresh": True,
            "telemetry_gate_free_tier_guardrails_bounded": bool(
                free_tier_guardrails["bounded_against_starter"]
            ),
            "telemetry_gate_free_tier_margin_guarded": free_tier_margin_guarded,
        },
    }


async def collect_snapshot(
    *,
    window_start: datetime,
    window_end_exclusive: datetime,
    label: str,
) -> dict[str, Any]:
    async with async_session_maker() as db:
        db_engine = str(getattr(getattr(db, "bind", None), "dialect", None).name)  # type: ignore[union-attr]
        subscription_snapshot = await _fetch_subscription_snapshot(
            db,
            window_start=window_start,
            window_end_exclusive=window_end_exclusive,
        )
        llm_snapshot = await _fetch_llm_usage_snapshot(
            db,
            window_start=window_start,
            window_end_exclusive=window_end_exclusive,
        )
    return _build_snapshot_payload(
        window_start=window_start,
        window_end_exclusive=window_end_exclusive,
        label=label,
        db_engine=db_engine,
        subscription_snapshot=subscription_snapshot,
        llm_snapshot=llm_snapshot,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect monthly finance telemetry snapshot from database.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON path for telemetry snapshot.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Window start date (YYYY-MM-DD). Defaults to previous full month start.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Window end date (YYYY-MM-DD). Defaults to previous full month end.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional window label override.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.start_date and args.end_date:
        start_date = _parse_date(str(args.start_date), field="start_date")
        end_date = _parse_date(str(args.end_date), field="end_date")
    elif args.start_date or args.end_date:
        raise ValueError("start_date and end_date must be provided together")
    else:
        start_date, end_date = _default_window()

    window_start, window_end_exclusive = _window_bounds(start_date, end_date)
    label = str(args.label).strip() if args.label else f"{start_date}_{end_date}"
    payload = asyncio.run(
        collect_snapshot(
            window_start=window_start,
            window_end_exclusive=window_end_exclusive,
            label=label,
        )
    )

    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Finance telemetry snapshot written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
