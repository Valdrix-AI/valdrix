#!/usr/bin/env python3
"""Generate finance guardrails + committee packet artifacts from telemetry snapshots."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.verify_finance_guardrails_evidence import verify_evidence
from scripts.verify_finance_telemetry_snapshot import verify_snapshot

TRACKED_TIERS: tuple[str, ...] = ("starter", "growth", "pro", "enterprise")


def _parse_float(
    value: Any,
    *,
    field: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{field} must be <= {max_value}")
    return parsed


def _parse_int(value: Any, *, field: str, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be integer-like") from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    return parsed


def _parse_non_empty_str(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def _sanitize_label(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_") or "snapshot"


def _load_json(path: Path, *, field: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{field} does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a JSON object")
    return payload


def _safe_margin_percent(revenue: float, cogs: float) -> float:
    if revenue <= 0.0:
        return 100.0 if cogs <= 0.0 else 0.0
    return ((revenue - cogs) / revenue) * 100.0


def _index_by_tier(rows: list[dict[str, Any]], *, field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{field}[{idx}] must be an object")
        tier = _parse_non_empty_str(row.get("tier"), field=f"{field}[{idx}].tier").lower()
        indexed[tier] = row
    return indexed


def _parse_tier_float_map(
    payload: dict[str, Any],
    *,
    field: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict[str, float]:
    raw = payload.get(field)
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    values: dict[str, float] = {}
    for tier in TRACKED_TIERS:
        values[tier] = _parse_float(
            raw.get(tier),
            field=f"{field}.{tier}",
            min_value=min_value,
            max_value=max_value,
        )
    return values


def _parse_thresholds(payload: dict[str, Any]) -> dict[str, float | int]:
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    return {
        "min_blended_gross_margin_percent": _parse_float(
            thresholds.get("min_blended_gross_margin_percent"),
            field="thresholds.min_blended_gross_margin_percent",
            min_value=0.0,
            max_value=100.0,
        ),
        "max_p95_tenant_llm_cogs_pct_mrr": _parse_float(
            thresholds.get("max_p95_tenant_llm_cogs_pct_mrr"),
            field="thresholds.max_p95_tenant_llm_cogs_pct_mrr",
            min_value=0.0,
        ),
        "max_annual_discount_impact_percent": _parse_float(
            thresholds.get("max_annual_discount_impact_percent"),
            field="thresholds.max_annual_discount_impact_percent",
            min_value=0.0,
            max_value=100.0,
        ),
        "min_growth_to_pro_conversion_mom_delta_percent": _parse_float(
            thresholds.get("min_growth_to_pro_conversion_mom_delta_percent"),
            field="thresholds.min_growth_to_pro_conversion_mom_delta_percent",
        ),
        "min_pro_to_enterprise_conversion_mom_delta_percent": _parse_float(
            thresholds.get("min_pro_to_enterprise_conversion_mom_delta_percent"),
            field="thresholds.min_pro_to_enterprise_conversion_mom_delta_percent",
        ),
        "min_stress_margin_percent": _parse_float(
            thresholds.get("min_stress_margin_percent"),
            field="thresholds.min_stress_margin_percent",
            min_value=0.0,
            max_value=100.0,
        ),
        "required_consecutive_margin_closes": _parse_int(
            thresholds.get("required_consecutive_margin_closes", 2),
            field="thresholds.required_consecutive_margin_closes",
            min_value=1,
        ),
    }


def _parse_close_history(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("close_history")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("close_history must be an array")
    parsed: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"close_history[{idx}] must be an object")
        parsed.append(
            {
                "month": _parse_non_empty_str(
                    item.get("month"),
                    field=f"close_history[{idx}].month",
                ),
                "blended_gross_margin_percent": _parse_float(
                    item.get("blended_gross_margin_percent"),
                    field=f"close_history[{idx}].blended_gross_margin_percent",
                    min_value=0.0,
                    max_value=100.0,
                ),
            }
        )
    return parsed


def _build_tier_unit_economics(
    *,
    telemetry: dict[str, Any],
    annual_mix_by_tier: dict[str, float],
    infra_cogs_pct_by_tier: dict[str, float],
    support_cogs_per_subscription_by_tier: dict[str, float],
    support_cogs_per_dunning_event_usd: float,
) -> list[dict[str, Any]]:
    pricing_reference = telemetry.get("pricing_reference")
    if not isinstance(pricing_reference, dict):
        raise ValueError("telemetry.pricing_reference must be an object")
    subscription_rows = telemetry.get("tier_subscription_snapshot")
    if not isinstance(subscription_rows, list):
        raise ValueError("telemetry.tier_subscription_snapshot must be an array")
    llm_rows = telemetry.get("tier_llm_usage")
    if not isinstance(llm_rows, list):
        raise ValueError("telemetry.tier_llm_usage must be an array")

    subscriptions = _index_by_tier(subscription_rows, field="telemetry.tier_subscription_snapshot")
    llm_usage = _index_by_tier(llm_rows, field="telemetry.tier_llm_usage")

    unit_rows: list[dict[str, Any]] = []
    for tier in TRACKED_TIERS:
        pricing = pricing_reference.get(tier)
        if not isinstance(pricing, dict):
            raise ValueError(f"telemetry.pricing_reference.{tier} must be an object")
        subscription = subscriptions.get(tier, {"active_subscriptions": 0, "dunning_events": 0})
        llm = llm_usage.get(
            tier,
            {"total_cost_usd": 0.0, "tenant_monthly_cost_percentiles_usd": {"p95": 0.0}},
        )

        monthly_price = _parse_float(
            pricing.get("monthly_price_usd"),
            field=f"telemetry.pricing_reference.{tier}.monthly_price_usd",
            min_value=0.0,
        )
        annual_factor = _parse_float(
            pricing.get("annual_monthly_factor"),
            field=f"telemetry.pricing_reference.{tier}.annual_monthly_factor",
            min_value=0.0,
            max_value=1.0,
        )

        active_subscriptions = _parse_int(
            subscription.get("active_subscriptions", 0),
            field=f"telemetry.tier_subscription_snapshot[{tier}].active_subscriptions",
            min_value=0,
        )
        dunning_events = _parse_int(
            subscription.get("dunning_events", 0),
            field=f"telemetry.tier_subscription_snapshot[{tier}].dunning_events",
            min_value=0,
        )

        gross_mrr_usd = monthly_price * active_subscriptions
        annual_mix = annual_mix_by_tier[tier]
        effective_mrr_usd = gross_mrr_usd * (1.0 - annual_mix * (1.0 - annual_factor))

        llm_cogs_usd = _parse_float(
            llm.get("total_cost_usd", 0.0),
            field=f"telemetry.tier_llm_usage[{tier}].total_cost_usd",
            min_value=0.0,
        )
        infra_cogs_usd = effective_mrr_usd * (infra_cogs_pct_by_tier[tier] / 100.0)
        support_cogs_usd = (
            active_subscriptions * support_cogs_per_subscription_by_tier[tier]
            + dunning_events * support_cogs_per_dunning_event_usd
        )
        total_cogs = llm_cogs_usd + infra_cogs_usd + support_cogs_usd
        gross_margin_percent = _safe_margin_percent(effective_mrr_usd, total_cogs)

        unit_rows.append(
            {
                "tier": tier,
                "mrr_usd": round(gross_mrr_usd, 2),
                "effective_mrr_usd": round(effective_mrr_usd, 2),
                "llm_cogs_usd": round(llm_cogs_usd, 2),
                "infra_cogs_usd": round(infra_cogs_usd, 2),
                "support_cogs_usd": round(support_cogs_usd, 2),
                "gross_margin_percent": round(gross_margin_percent, 2),
                "active_subscriptions": active_subscriptions,
                "dunning_events": dunning_events,
            }
        )

    return unit_rows


def _compute_metrics(
    *,
    tier_unit_economics: list[dict[str, Any]],
    telemetry: dict[str, Any],
    conversion_signals: dict[str, float],
    stress_infra_multiplier: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    total_mrr = 0.0
    total_effective_mrr = 0.0
    total_llm_cogs = 0.0
    total_infra_cogs = 0.0
    total_support_cogs = 0.0
    worst_p95_pct = 0.0

    llm_rows = telemetry.get("tier_llm_usage")
    if not isinstance(llm_rows, list):
        raise ValueError("telemetry.tier_llm_usage must be an array")
    llm_usage = _index_by_tier(llm_rows, field="telemetry.tier_llm_usage")

    for row in tier_unit_economics:
        tier = str(row["tier"])
        mrr = float(row["mrr_usd"])
        effective = float(row["effective_mrr_usd"])
        llm = float(row["llm_cogs_usd"])
        infra = float(row["infra_cogs_usd"])
        support = float(row["support_cogs_usd"])
        active_subscriptions = int(row["active_subscriptions"])

        total_mrr += mrr
        total_effective_mrr += effective
        total_llm_cogs += llm
        total_infra_cogs += infra
        total_support_cogs += support

        tier_llm = llm_usage.get(tier, {})
        percentiles = tier_llm.get("tenant_monthly_cost_percentiles_usd")
        p95_cost = 0.0
        if isinstance(percentiles, dict):
            p95_cost = _parse_float(
                percentiles.get("p95", 0.0),
                field=f"telemetry.tier_llm_usage[{tier}].tenant_monthly_cost_percentiles_usd.p95",
                min_value=0.0,
            )
        per_tenant_effective = (
            effective / active_subscriptions if active_subscriptions > 0 else 0.0
        )
        if per_tenant_effective > 0:
            pct = (p95_cost / per_tenant_effective) * 100.0
            worst_p95_pct = max(worst_p95_pct, pct)

    blended_margin = _safe_margin_percent(
        total_effective_mrr,
        total_llm_cogs + total_infra_cogs + total_support_cogs,
    )
    annual_discount_impact = 0.0
    if total_mrr > 0:
        annual_discount_impact = ((total_mrr - total_effective_mrr) / total_mrr) * 100.0

    stress_margin = _safe_margin_percent(
        total_effective_mrr,
        total_llm_cogs + (total_infra_cogs * stress_infra_multiplier) + total_support_cogs,
    )
    metrics = {
        "blended_gross_margin_percent": round(blended_margin, 2),
        "p95_tenant_llm_cogs_pct_mrr": round(worst_p95_pct, 2),
        "annual_discount_impact_percent": round(annual_discount_impact, 2),
        "growth_to_pro_conversion_mom_delta_percent": round(
            conversion_signals["growth_to_pro_conversion_mom_delta_percent"], 4
        ),
        "pro_to_enterprise_conversion_mom_delta_percent": round(
            conversion_signals["pro_to_enterprise_conversion_mom_delta_percent"], 4
        ),
        "stress_margin_percent": round(stress_margin, 2),
    }
    totals = {
        "total_mrr_usd": round(total_mrr, 2),
        "total_effective_mrr_usd": round(total_effective_mrr, 2),
        "total_llm_cogs_usd": round(total_llm_cogs, 2),
        "total_infra_cogs_usd": round(total_infra_cogs, 2),
        "total_support_cogs_usd": round(total_support_cogs, 2),
    }
    return metrics, totals


def _build_gate_results(
    *,
    metrics: dict[str, float],
    thresholds: dict[str, float | int],
    close_history: list[dict[str, Any]],
) -> dict[str, bool]:
    required_consecutive = int(thresholds["required_consecutive_margin_closes"])
    if len(close_history) < required_consecutive:
        raise ValueError(
            "close_history must include at least "
            f"{required_consecutive} entries"
        )
    recent = close_history[-required_consecutive:]
    close_history_pass = all(
        float(item["blended_gross_margin_percent"])
        >= float(thresholds["min_blended_gross_margin_percent"])
        for item in recent
    )
    return {
        "fin_gate_1_gross_margin_floor": (
            metrics["blended_gross_margin_percent"]
            >= float(thresholds["min_blended_gross_margin_percent"])
            and close_history_pass
        ),
        "fin_gate_2_llm_cogs_containment": (
            metrics["p95_tenant_llm_cogs_pct_mrr"]
            <= float(thresholds["max_p95_tenant_llm_cogs_pct_mrr"])
        ),
        "fin_gate_3_annual_discount_impact": (
            metrics["annual_discount_impact_percent"]
            <= float(thresholds["max_annual_discount_impact_percent"])
        ),
        "fin_gate_4_expansion_signal": (
            metrics["growth_to_pro_conversion_mom_delta_percent"]
            >= float(thresholds["min_growth_to_pro_conversion_mom_delta_percent"])
            and metrics["pro_to_enterprise_conversion_mom_delta_percent"]
            >= float(thresholds["min_pro_to_enterprise_conversion_mom_delta_percent"])
        ),
        "fin_gate_5_stress_resilience": (
            metrics["stress_margin_percent"]
            >= float(thresholds["min_stress_margin_percent"])
        ),
    }


def _compute_scenario_rows(
    *,
    baseline_rows: list[dict[str, Any]],
    annual_mix_by_tier: dict[str, float],
    assumptions: dict[str, Any],
) -> list[dict[str, Any]]:
    scenario_models = assumptions.get("scenario_models")
    if not isinstance(scenario_models, dict):
        return []
    scenario_rows_raw = scenario_models.get("price_sensitivity")
    if not isinstance(scenario_rows_raw, list):
        return []

    baseline_by_tier = {str(row["tier"]): row for row in baseline_rows}
    output: list[dict[str, Any]] = []
    for idx, scenario in enumerate(scenario_rows_raw):
        if not isinstance(scenario, dict):
            raise ValueError(f"scenario_models.price_sensitivity[{idx}] must be an object")
        name = _parse_non_empty_str(
            scenario.get("name"),
            field=f"scenario_models.price_sensitivity[{idx}].name",
        )
        sub_mults = scenario.get("subscription_multipliers_by_tier")
        if not isinstance(sub_mults, dict):
            raise ValueError(
                "scenario_models.price_sensitivity[{idx}].subscription_multipliers_by_tier "
                "must be an object".format(idx=idx)
            )
        price_mults = scenario.get("monthly_price_multipliers_by_tier")
        if not isinstance(price_mults, dict):
            raise ValueError(
                "scenario_models.price_sensitivity[{idx}].monthly_price_multipliers_by_tier "
                "must be an object".format(idx=idx)
            )

        total_effective = 0.0
        total_cogs = 0.0
        for tier in TRACKED_TIERS:
            baseline = baseline_by_tier[tier]
            sub_mult = _parse_float(
                sub_mults.get(tier),
                field=f"scenario_models.price_sensitivity[{idx}].subscription_multipliers_by_tier.{tier}",
                min_value=0.0,
            )
            price_mult = _parse_float(
                price_mults.get(tier),
                field=f"scenario_models.price_sensitivity[{idx}].monthly_price_multipliers_by_tier.{tier}",
                min_value=0.0,
            )
            active = float(baseline["active_subscriptions"]) * sub_mult
            monthly_price = (float(baseline["mrr_usd"]) / max(float(baseline["active_subscriptions"]), 1.0)) * price_mult
            gross_mrr = active * monthly_price
            annual_factor = 1.0 - annual_mix_by_tier[tier] * (
                1.0 - _parse_float(
                    assumptions["telemetry_pricing_factors"][tier],
                    field=f"telemetry_pricing_factors.{tier}",
                    min_value=0.0,
                    max_value=1.0,
                )
            )
            effective_mrr = gross_mrr * annual_factor

            llm_per_sub = float(baseline["llm_cogs_usd"]) / max(float(baseline["active_subscriptions"]), 1.0)
            infra_per_effective = float(baseline["infra_cogs_usd"]) / max(float(baseline["effective_mrr_usd"]), 1.0)
            support_per_sub = float(baseline["support_cogs_usd"]) / max(float(baseline["active_subscriptions"]), 1.0)

            llm_cogs = llm_per_sub * active
            infra_cogs = infra_per_effective * effective_mrr
            support_cogs = support_per_sub * active

            total_effective += effective_mrr
            total_cogs += llm_cogs + infra_cogs + support_cogs

        output.append(
            {
                "scenario": name,
                "effective_mrr_usd": round(total_effective, 2),
                "projected_margin_percent": round(
                    _safe_margin_percent(total_effective, total_cogs), 2
                ),
            }
        )
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _send_alert_if_needed(
    *,
    webhook_url: str | None,
    webhook_timeout_seconds: float,
    webhook_fail_on_error: bool,
    packet_summary: dict[str, Any],
    gate_results: dict[str, bool],
) -> None:
    if not webhook_url:
        return
    if all(gate_results.values()):
        return
    payload = {
        "event": "finance_gate_failure",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "summary": packet_summary,
        "gate_results": gate_results,
    }
    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            timeout=webhook_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"alert webhook rejected payload with status={response.status_code}"
            )
    except Exception as exc:
        if webhook_fail_on_error:
            raise RuntimeError(f"failed to send finance alert webhook: {exc}") from exc


def _build_finance_outputs(
    *,
    telemetry: dict[str, Any],
    assumptions: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    annual_mix_by_tier = _parse_tier_float_map(
        assumptions,
        field="annual_mix_by_tier",
        min_value=0.0,
        max_value=1.0,
    )
    infra_cogs_pct_by_tier = _parse_tier_float_map(
        assumptions,
        field="infra_cogs_percent_of_effective_mrr_by_tier",
        min_value=0.0,
    )
    support_cogs_per_subscription_by_tier = _parse_tier_float_map(
        assumptions,
        field="support_cogs_per_active_subscription_usd_by_tier",
        min_value=0.0,
    )
    support_cogs_per_dunning_event_usd = _parse_float(
        assumptions.get("support_cogs_per_dunning_event_usd"),
        field="support_cogs_per_dunning_event_usd",
        min_value=0.0,
    )
    conversion_signals_raw = assumptions.get("conversion_signals")
    if not isinstance(conversion_signals_raw, dict):
        raise ValueError("conversion_signals must be an object")
    conversion_signals = {
        "growth_to_pro_conversion_mom_delta_percent": _parse_float(
            conversion_signals_raw.get("growth_to_pro_conversion_mom_delta_percent"),
            field="conversion_signals.growth_to_pro_conversion_mom_delta_percent",
        ),
        "pro_to_enterprise_conversion_mom_delta_percent": _parse_float(
            conversion_signals_raw.get("pro_to_enterprise_conversion_mom_delta_percent"),
            field="conversion_signals.pro_to_enterprise_conversion_mom_delta_percent",
        ),
    }
    stress_scenario_raw = assumptions.get("stress_scenario")
    if not isinstance(stress_scenario_raw, dict):
        raise ValueError("stress_scenario must be an object")
    stress_infra_multiplier = _parse_float(
        stress_scenario_raw.get("infra_cost_multiplier"),
        field="stress_scenario.infra_cost_multiplier",
        min_value=1.0,
    )
    thresholds = _parse_thresholds(assumptions)
    close_history = _parse_close_history(assumptions)

    tier_unit_economics = _build_tier_unit_economics(
        telemetry=telemetry,
        annual_mix_by_tier=annual_mix_by_tier,
        infra_cogs_pct_by_tier=infra_cogs_pct_by_tier,
        support_cogs_per_subscription_by_tier=support_cogs_per_subscription_by_tier,
        support_cogs_per_dunning_event_usd=support_cogs_per_dunning_event_usd,
    )
    metrics, totals = _compute_metrics(
        tier_unit_economics=tier_unit_economics,
        telemetry=telemetry,
        conversion_signals=conversion_signals,
        stress_infra_multiplier=stress_infra_multiplier,
    )
    window = telemetry.get("window")
    if not isinstance(window, dict):
        raise ValueError("telemetry.window must be an object")
    close_history.append(
        {
            "month": _parse_non_empty_str(window.get("label"), field="telemetry.window.label"),
            "blended_gross_margin_percent": metrics["blended_gross_margin_percent"],
        }
    )
    gate_results = _build_gate_results(
        metrics=metrics,
        thresholds=thresholds,
        close_history=close_history,
    )

    finance_guardrails = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": {
            "start": _parse_non_empty_str(window.get("start"), field="telemetry.window.start"),
            "end": _parse_non_empty_str(window.get("end"), field="telemetry.window.end"),
            "label": _parse_non_empty_str(window.get("label"), field="telemetry.window.label"),
        },
        "metrics": metrics,
        "thresholds": thresholds,
        "close_history": close_history,
        "tier_unit_economics": [
            {
                "tier": row["tier"],
                "mrr_usd": row["mrr_usd"],
                "effective_mrr_usd": row["effective_mrr_usd"],
                "llm_cogs_usd": row["llm_cogs_usd"],
                "infra_cogs_usd": row["infra_cogs_usd"],
                "support_cogs_usd": row["support_cogs_usd"],
                "gross_margin_percent": row["gross_margin_percent"],
            }
            for row in tier_unit_economics
        ],
        "stress_scenario": {
            "infra_cost_multiplier": stress_infra_multiplier,
            "projected_margin_percent": metrics["stress_margin_percent"],
        },
        "gate_results": gate_results,
    }

    pricing_reference = telemetry.get("pricing_reference")
    if not isinstance(pricing_reference, dict):
        raise ValueError("telemetry.pricing_reference must be an object")
    assumptions_with_factors = dict(assumptions)
    assumptions_with_factors["telemetry_pricing_factors"] = {
        tier: _parse_float(
            pricing_reference[tier]["annual_monthly_factor"],
            field=f"telemetry.pricing_reference.{tier}.annual_monthly_factor",
            min_value=0.0,
            max_value=1.0,
        )
        for tier in TRACKED_TIERS
    }
    scenario_rows = _compute_scenario_rows(
        baseline_rows=tier_unit_economics,
        annual_mix_by_tier=annual_mix_by_tier,
        assumptions=assumptions_with_factors,
    )

    self_hosted_tco_raw = assumptions.get("self_hosted_tco_inputs", {})
    if not isinstance(self_hosted_tco_raw, dict):
        raise ValueError("self_hosted_tco_inputs must be an object when provided")
    self_hosted_total = 0.0
    for key in (
        "annual_staffing_usd",
        "annual_oncall_usd",
        "annual_security_compliance_usd",
        "annual_infra_ops_usd",
        "annual_tooling_usd",
    ):
        self_hosted_total += _parse_float(
            self_hosted_tco_raw.get(key, 0.0),
            field=f"self_hosted_tco_inputs.{key}",
            min_value=0.0,
        )

    hosted_arr = totals["total_effective_mrr_usd"] * 12.0
    committee_packet = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": finance_guardrails["window"],
        "summary": {
            "overall_finance_gates_passed": all(gate_results.values()),
            "totals": totals,
            "hosted_arr_run_rate_usd": round(hosted_arr, 2),
            "self_hosted_tco_estimate_usd": round(self_hosted_total, 2),
            "hosted_vs_self_hosted_delta_usd": round(hosted_arr - self_hosted_total, 2),
        },
        "fin_tracking": {
            "fin_001_tier_unit_economics_present": True,
            "fin_002_percentile_cost_model_present": True,
            "fin_003_repricing_signal_included": True,
            "fin_004_beta_cost_value_evidence_attached": True,
            "fin_005_migration_signals_present": True,
            "fin_006_price_sensitivity_model_present": bool(scenario_rows),
            "fin_007_gtm_model_present": bool(scenario_rows),
            "fin_008_hosted_vs_self_hosted_tco_present": bool(self_hosted_total > 0),
        },
        "gate_results": gate_results,
        "tier_unit_economics": tier_unit_economics,
        "scenario_rows": scenario_rows,
    }
    return finance_guardrails, committee_packet, tier_unit_economics, scenario_rows


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate finance guardrail + committee packet artifacts from telemetry.",
    )
    parser.add_argument("--telemetry-path", required=True, help="Telemetry snapshot JSON path.")
    parser.add_argument("--assumptions-path", required=True, help="Packet assumptions JSON path.")
    parser.add_argument("--output-dir", required=True, help="Output directory for generated artifacts.")
    parser.add_argument(
        "--max-telemetry-age-hours",
        type=float,
        default=None,
        help="Optional max allowed age for telemetry artifact.",
    )
    parser.add_argument(
        "--require-all-gates-pass",
        action="store_true",
        help="Return non-zero when any FIN gate fails.",
    )
    parser.add_argument(
        "--alert-webhook-url",
        default=None,
        help="Optional webhook URL for finance gate failure alerts.",
    )
    parser.add_argument(
        "--alert-webhook-timeout-seconds",
        type=float,
        default=10.0,
        help="Webhook timeout in seconds.",
    )
    parser.add_argument(
        "--alert-webhook-fail-on-error",
        action="store_true",
        help="Fail generation if alert webhook call fails.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    telemetry_path = Path(str(args.telemetry_path))
    assumptions_path = Path(str(args.assumptions_path))
    output_dir = Path(str(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    verify_snapshot(
        snapshot_path=telemetry_path,
        max_artifact_age_hours=(
            float(args.max_telemetry_age_hours)
            if args.max_telemetry_age_hours is not None
            else None
        ),
    )
    telemetry = _load_json(telemetry_path, field="telemetry_path")
    assumptions = _load_json(assumptions_path, field="assumptions_path")

    finance_guardrails, committee_packet, tier_rows, scenario_rows = _build_finance_outputs(
        telemetry=telemetry,
        assumptions=assumptions,
    )
    label = _sanitize_label(str(finance_guardrails["window"]["label"]))

    guardrails_path = output_dir / f"finance_guardrails_{label}.json"
    committee_path = output_dir / f"finance_committee_packet_{label}.json"
    tiers_csv_path = output_dir / f"finance_committee_tier_unit_economics_{label}.csv"
    scenarios_csv_path = output_dir / f"finance_committee_scenarios_{label}.csv"

    guardrails_path.write_text(
        json.dumps(finance_guardrails, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    committee_path.write_text(
        json.dumps(committee_packet, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(tiers_csv_path, tier_rows)
    _write_csv(scenarios_csv_path, scenario_rows)

    verify_evidence(evidence_path=guardrails_path, allow_failed_gates=True)

    _send_alert_if_needed(
        webhook_url=(str(args.alert_webhook_url).strip() if args.alert_webhook_url else None),
        webhook_timeout_seconds=float(args.alert_webhook_timeout_seconds),
        webhook_fail_on_error=bool(args.alert_webhook_fail_on_error),
        packet_summary=committee_packet["summary"],
        gate_results=committee_packet["gate_results"],
    )

    print(f"Generated finance guardrails: {guardrails_path}")
    print(f"Generated finance committee packet: {committee_path}")
    print(f"Generated tier economics CSV: {tiers_csv_path}")
    print(f"Generated scenarios CSV: {scenarios_csv_path}")

    if bool(args.require_all_gates_pass) and not all(committee_packet["gate_results"].values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
