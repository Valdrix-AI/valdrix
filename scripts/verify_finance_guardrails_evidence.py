#!/usr/bin/env python3
"""Validate finance guardrail evidence for PKG/FIN release-gate decisions."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_iso_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty ISO-8601 datetime")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


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


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Finance evidence file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Finance evidence JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Finance evidence payload must be a JSON object")
    return payload


def _approx_equal(lhs: float, rhs: float, *, places: int = 2) -> bool:
    return round(float(lhs), places) == round(float(rhs), places)


def _calc_margin_percent(revenue: float, total_cogs: float) -> float:
    if revenue <= 0:
        raise ValueError("effective revenue must be > 0 for gross margin calculation")
    return ((revenue - total_cogs) / revenue) * 100.0


def verify_evidence(
    *,
    evidence_path: Path,
    max_artifact_age_hours: float | None = None,
    allow_failed_gates: bool = False,
) -> int:
    payload = _load_payload(evidence_path)

    captured_at = _parse_iso_utc(payload.get("captured_at"), field="captured_at")
    if max_artifact_age_hours is not None:
        max_age = _parse_float(
            max_artifact_age_hours,
            field="max_artifact_age_hours",
            min_value=0.01,
        )
        age_hours = (datetime.now(timezone.utc) - captured_at).total_seconds() / 3600.0
        if age_hours > max_age:
            raise ValueError(
                f"captured_at is too old ({age_hours:.2f}h > max {max_age:.2f}h)"
            )

    window = payload.get("window")
    if not isinstance(window, dict):
        raise ValueError("window must be an object")
    window_start = _parse_iso_utc(window.get("start"), field="window.start")
    window_end = _parse_iso_utc(window.get("end"), field="window.end")
    if window_end < window_start:
        raise ValueError("window.end must be >= window.start")

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    gate_results = payload.get("gate_results")
    if not isinstance(gate_results, dict):
        raise ValueError("gate_results must be an object")

    blended_margin = _parse_float(
        metrics.get("blended_gross_margin_percent"),
        field="metrics.blended_gross_margin_percent",
        min_value=0.0,
        max_value=100.0,
    )
    p95_llm_cogs_pct = _parse_float(
        metrics.get("p95_tenant_llm_cogs_pct_mrr"),
        field="metrics.p95_tenant_llm_cogs_pct_mrr",
        min_value=0.0,
    )
    annual_discount_impact = _parse_float(
        metrics.get("annual_discount_impact_percent"),
        field="metrics.annual_discount_impact_percent",
        min_value=0.0,
        max_value=100.0,
    )
    growth_to_pro_delta = _parse_float(
        metrics.get("growth_to_pro_conversion_mom_delta_percent"),
        field="metrics.growth_to_pro_conversion_mom_delta_percent",
    )
    pro_to_ent_delta = _parse_float(
        metrics.get("pro_to_enterprise_conversion_mom_delta_percent"),
        field="metrics.pro_to_enterprise_conversion_mom_delta_percent",
    )
    stress_margin = _parse_float(
        metrics.get("stress_margin_percent"),
        field="metrics.stress_margin_percent",
        min_value=0.0,
        max_value=100.0,
    )

    min_blended_margin = _parse_float(
        thresholds.get("min_blended_gross_margin_percent"),
        field="thresholds.min_blended_gross_margin_percent",
        min_value=0.0,
        max_value=100.0,
    )
    max_p95_llm_cogs_pct = _parse_float(
        thresholds.get("max_p95_tenant_llm_cogs_pct_mrr"),
        field="thresholds.max_p95_tenant_llm_cogs_pct_mrr",
        min_value=0.0,
    )
    max_annual_discount_impact = _parse_float(
        thresholds.get("max_annual_discount_impact_percent"),
        field="thresholds.max_annual_discount_impact_percent",
        min_value=0.0,
        max_value=100.0,
    )
    min_growth_to_pro_delta = _parse_float(
        thresholds.get("min_growth_to_pro_conversion_mom_delta_percent"),
        field="thresholds.min_growth_to_pro_conversion_mom_delta_percent",
    )
    min_pro_to_ent_delta = _parse_float(
        thresholds.get("min_pro_to_enterprise_conversion_mom_delta_percent"),
        field="thresholds.min_pro_to_enterprise_conversion_mom_delta_percent",
    )
    min_stress_margin = _parse_float(
        thresholds.get("min_stress_margin_percent"),
        field="thresholds.min_stress_margin_percent",
        min_value=0.0,
        max_value=100.0,
    )
    required_consecutive_closes = _parse_int(
        thresholds.get("required_consecutive_margin_closes", 1),
        field="thresholds.required_consecutive_margin_closes",
        min_value=1,
    )

    close_history = payload.get("close_history")
    if not isinstance(close_history, list):
        raise ValueError("close_history must be an array")
    if len(close_history) < required_consecutive_closes:
        raise ValueError(
            "close_history must include at least "
            f"{required_consecutive_closes} entries"
        )
    closes_all_pass = True
    for idx, close in enumerate(close_history[-required_consecutive_closes:]):
        if not isinstance(close, dict):
            raise ValueError(f"close_history[{idx}] must be an object")
        margin = _parse_float(
            close.get("blended_gross_margin_percent"),
            field=f"close_history[{idx}].blended_gross_margin_percent",
            min_value=0.0,
            max_value=100.0,
        )
        if margin < min_blended_margin:
            closes_all_pass = False

    tiers = payload.get("tier_unit_economics")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tier_unit_economics must be a non-empty array")
    required_tiers = {"starter", "growth", "pro", "enterprise"}
    seen_tiers: set[str] = set()
    gross_revenue_sum = 0.0
    effective_revenue_sum = 0.0
    total_cogs_sum = 0.0
    for idx, item in enumerate(tiers):
        if not isinstance(item, dict):
            raise ValueError(f"tier_unit_economics[{idx}] must be an object")
        tier = str(item.get("tier") or "").strip().lower()
        if not tier:
            raise ValueError(f"tier_unit_economics[{idx}].tier must be a non-empty string")
        seen_tiers.add(tier)

        mrr_usd = _parse_float(
            item.get("mrr_usd"),
            field=f"tier_unit_economics[{idx}].mrr_usd",
            min_value=0.0,
        )
        effective_mrr_usd = _parse_float(
            item.get("effective_mrr_usd"),
            field=f"tier_unit_economics[{idx}].effective_mrr_usd",
            min_value=0.0,
        )
        if effective_mrr_usd > mrr_usd:
            raise ValueError(
                f"tier_unit_economics[{idx}].effective_mrr_usd cannot exceed mrr_usd"
            )
        llm_cogs_usd = _parse_float(
            item.get("llm_cogs_usd"),
            field=f"tier_unit_economics[{idx}].llm_cogs_usd",
            min_value=0.0,
        )
        infra_cogs_usd = _parse_float(
            item.get("infra_cogs_usd"),
            field=f"tier_unit_economics[{idx}].infra_cogs_usd",
            min_value=0.0,
        )
        support_cogs_usd = _parse_float(
            item.get("support_cogs_usd"),
            field=f"tier_unit_economics[{idx}].support_cogs_usd",
            min_value=0.0,
        )
        gross_margin_percent = _parse_float(
            item.get("gross_margin_percent"),
            field=f"tier_unit_economics[{idx}].gross_margin_percent",
            min_value=0.0,
            max_value=100.0,
        )
        tier_margin = _calc_margin_percent(
            effective_mrr_usd,
            llm_cogs_usd + infra_cogs_usd + support_cogs_usd,
        )
        if not _approx_equal(tier_margin, gross_margin_percent):
            raise ValueError(
                f"tier_unit_economics[{idx}].gross_margin_percent must match "
                "computed margin from effective_mrr_usd and cogs"
            )
        gross_revenue_sum += mrr_usd
        effective_revenue_sum += effective_mrr_usd
        total_cogs_sum += llm_cogs_usd + infra_cogs_usd + support_cogs_usd

    missing_tiers = required_tiers.difference(seen_tiers)
    if missing_tiers:
        missing_rendered = ", ".join(sorted(missing_tiers))
        raise ValueError(f"tier_unit_economics missing required tiers: {missing_rendered}")

    blended_margin_computed = _calc_margin_percent(effective_revenue_sum, total_cogs_sum)
    if not _approx_equal(blended_margin_computed, blended_margin):
        raise ValueError(
            "metrics.blended_gross_margin_percent must match "
            "computed blended margin from tier_unit_economics"
        )
    if gross_revenue_sum <= 0:
        raise ValueError("sum(tier_unit_economics[*].mrr_usd) must be > 0")
    annual_discount_computed = ((gross_revenue_sum - effective_revenue_sum) / gross_revenue_sum) * 100.0
    if not _approx_equal(annual_discount_computed, annual_discount_impact):
        raise ValueError(
            "metrics.annual_discount_impact_percent must match "
            "computed impact from tier_unit_economics"
        )

    stress = payload.get("stress_scenario")
    if not isinstance(stress, dict):
        raise ValueError("stress_scenario must be an object")
    _parse_float(
        stress.get("infra_cost_multiplier"),
        field="stress_scenario.infra_cost_multiplier",
        min_value=1.0,
    )
    projected_stress_margin = _parse_float(
        stress.get("projected_margin_percent"),
        field="stress_scenario.projected_margin_percent",
        min_value=0.0,
        max_value=100.0,
    )
    if not _approx_equal(projected_stress_margin, stress_margin):
        raise ValueError(
            "metrics.stress_margin_percent must equal "
            "stress_scenario.projected_margin_percent"
        )

    computed_gates = {
        "fin_gate_1_gross_margin_floor": (
            blended_margin >= min_blended_margin and closes_all_pass
        ),
        "fin_gate_2_llm_cogs_containment": p95_llm_cogs_pct <= max_p95_llm_cogs_pct,
        "fin_gate_3_annual_discount_impact": (
            annual_discount_impact <= max_annual_discount_impact
        ),
        "fin_gate_4_expansion_signal": (
            growth_to_pro_delta >= min_growth_to_pro_delta
            and pro_to_ent_delta >= min_pro_to_ent_delta
        ),
        "fin_gate_5_stress_resilience": stress_margin >= min_stress_margin,
    }
    for gate, expected in computed_gates.items():
        raw = gate_results.get(gate)
        if not isinstance(raw, bool):
            raise ValueError(f"gate_results.{gate} must be boolean")
        if raw is not expected:
            raise ValueError(
                f"gate_results.{gate} mismatch: payload={raw} computed={expected}"
            )
    if not all(computed_gates.values()) and not allow_failed_gates:
        failed = [name for name, ok in computed_gates.items() if not ok]
        raise ValueError(
            f"Finance guardrail verification failed for gates: {', '.join(failed)}"
        )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify finance guardrail evidence artifact used for PKG/FIN "
            "release and pricing decisions."
        )
    )
    parser.add_argument(
        "--evidence-path",
        required=True,
        help="Path to finance guardrail evidence JSON.",
    )
    parser.add_argument(
        "--max-artifact-age-hours",
        type=float,
        default=None,
        help="Optional max age of artifact in hours.",
    )
    parser.add_argument(
        "--allow-failed-gates",
        action="store_true",
        help=(
            "Validate artifact integrity while allowing computed FIN gates "
            "to fail."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    evidence_path = Path(str(args.evidence_path))
    verify_evidence(
        evidence_path=evidence_path,
        max_artifact_age_hours=(
            float(args.max_artifact_age_hours)
            if args.max_artifact_age_hours is not None
            else None
        ),
        allow_failed_gates=bool(args.allow_failed_gates),
    )
    print(f"Finance guardrail evidence verified: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
