#!/usr/bin/env python3
"""Validate finance telemetry snapshot artifacts used for FIN packet generation."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_TIERS = {"free", "starter", "growth", "pro", "enterprise"}


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


def _parse_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be boolean")


def _parse_non_empty_str(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Finance telemetry snapshot file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Finance telemetry snapshot JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Finance telemetry snapshot payload must be a JSON object")
    return payload


def verify_snapshot(
    *,
    snapshot_path: Path,
    max_artifact_age_hours: float | None = None,
) -> int:
    payload = _load_payload(snapshot_path)
    captured_at = _parse_iso_utc(payload.get("captured_at"), field="captured_at")

    artifact_fresh = True
    if max_artifact_age_hours is not None:
        max_age = _parse_float(
            max_artifact_age_hours,
            field="max_artifact_age_hours",
            min_value=0.01,
        )
        age_hours = (datetime.now(timezone.utc) - captured_at).total_seconds() / 3600.0
        artifact_fresh = age_hours <= max_age
        if not artifact_fresh:
            raise ValueError(
                f"captured_at is too old ({age_hours:.2f}h > max {max_age:.2f}h)"
            )

    window = payload.get("window")
    if not isinstance(window, dict):
        raise ValueError("window must be an object")
    window_start = _parse_iso_utc(window.get("start"), field="window.start")
    window_end = _parse_iso_utc(window.get("end"), field="window.end")
    _parse_non_empty_str(window.get("label"), field="window.label")
    window_valid = window_end >= window_start
    if not window_valid:
        raise ValueError("window.end must be >= window.start")
    if captured_at < window_end:
        raise ValueError("captured_at must be >= window.end")

    pricing_reference = payload.get("pricing_reference")
    if not isinstance(pricing_reference, dict):
        raise ValueError("pricing_reference must be an object")
    for tier in REQUIRED_TIERS:
        tier_ref = pricing_reference.get(tier)
        if not isinstance(tier_ref, dict):
            raise ValueError(f"pricing_reference.{tier} must be an object")
        monthly = _parse_float(
            tier_ref.get("monthly_price_usd"),
            field=f"pricing_reference.{tier}.monthly_price_usd",
            min_value=0.0,
        )
        annual = _parse_float(
            tier_ref.get("annual_price_usd"),
            field=f"pricing_reference.{tier}.annual_price_usd",
            min_value=0.0,
        )
        annual_factor = _parse_float(
            tier_ref.get("annual_monthly_factor"),
            field=f"pricing_reference.{tier}.annual_monthly_factor",
            min_value=0.0,
            max_value=1.0,
        )
        if monthly > 0.0 and annual > 0.0:
            expected_factor = annual / (monthly * 12.0)
            if round(annual_factor, 6) != round(expected_factor, 6):
                raise ValueError(
                    f"pricing_reference.{tier}.annual_monthly_factor must match "
                    "annual/monthly ratio"
                )

    subscription_rows = payload.get("tier_subscription_snapshot")
    if not isinstance(subscription_rows, list) or not subscription_rows:
        raise ValueError("tier_subscription_snapshot must be a non-empty array")
    llm_rows = payload.get("tier_llm_usage")
    if not isinstance(llm_rows, list) or not llm_rows:
        raise ValueError("tier_llm_usage must be a non-empty array")

    subscription_tiers: set[str] = set()
    for idx, row in enumerate(subscription_rows):
        if not isinstance(row, dict):
            raise ValueError(f"tier_subscription_snapshot[{idx}] must be an object")
        tier = _parse_non_empty_str(
            row.get("tier"),
            field=f"tier_subscription_snapshot[{idx}].tier",
        ).lower()
        subscription_tiers.add(tier)
        active_subscriptions = _parse_int(
            row.get("active_subscriptions"),
            field=f"tier_subscription_snapshot[{idx}].active_subscriptions",
            min_value=0,
        )
        total_tenants = _parse_int(
            row.get("total_tenants"),
            field=f"tier_subscription_snapshot[{idx}].total_tenants",
            min_value=0,
        )
        _parse_int(
            row.get("dunning_events"),
            field=f"tier_subscription_snapshot[{idx}].dunning_events",
            min_value=0,
        )
        if total_tenants > 0 and active_subscriptions > total_tenants:
            raise ValueError(
                f"tier_subscription_snapshot[{idx}].active_subscriptions "
                "cannot exceed total_tenants"
            )

    llm_tiers: set[str] = set()
    percentiles_valid = True
    for idx, row in enumerate(llm_rows):
        if not isinstance(row, dict):
            raise ValueError(f"tier_llm_usage[{idx}] must be an object")
        tier = _parse_non_empty_str(
            row.get("tier"),
            field=f"tier_llm_usage[{idx}].tier",
        ).lower()
        llm_tiers.add(tier)
        _parse_float(
            row.get("total_cost_usd"),
            field=f"tier_llm_usage[{idx}].total_cost_usd",
            min_value=0.0,
        )
        percentiles = row.get("tenant_monthly_cost_percentiles_usd")
        if not isinstance(percentiles, dict):
            raise ValueError(
                "tier_llm_usage[{idx}].tenant_monthly_cost_percentiles_usd must be "
                "an object".format(idx=idx)
            )
        p50 = _parse_float(
            percentiles.get("p50"),
            field=f"tier_llm_usage[{idx}].tenant_monthly_cost_percentiles_usd.p50",
            min_value=0.0,
        )
        p95 = _parse_float(
            percentiles.get("p95"),
            field=f"tier_llm_usage[{idx}].tenant_monthly_cost_percentiles_usd.p95",
            min_value=0.0,
        )
        p99 = _parse_float(
            percentiles.get("p99"),
            field=f"tier_llm_usage[{idx}].tenant_monthly_cost_percentiles_usd.p99",
            min_value=0.0,
        )
        if not (p50 <= p95 <= p99):
            percentiles_valid = False

    required_tiers_present = REQUIRED_TIERS.issubset(subscription_tiers) and REQUIRED_TIERS.issubset(llm_tiers)
    if not required_tiers_present:
        missing_sub = REQUIRED_TIERS.difference(subscription_tiers)
        missing_llm = REQUIRED_TIERS.difference(llm_tiers)
        raise ValueError(
            "Finance telemetry snapshot missing required tiers. "
            f"subscription_missing={sorted(missing_sub)} "
            f"llm_missing={sorted(missing_llm)}"
        )
    if not percentiles_valid:
        raise ValueError("tier_llm_usage percentiles must satisfy p50 <= p95 <= p99")

    free_tier_compute_guardrails = payload.get("free_tier_compute_guardrails")
    if not isinstance(free_tier_compute_guardrails, dict):
        raise ValueError("free_tier_compute_guardrails must be an object")
    free_tier_name = _parse_non_empty_str(
        free_tier_compute_guardrails.get("tier"),
        field="free_tier_compute_guardrails.tier",
    ).lower()
    if free_tier_name != "free":
        raise ValueError("free_tier_compute_guardrails.tier must be free")
    reference_tier_name = _parse_non_empty_str(
        free_tier_compute_guardrails.get("reference_tier"),
        field="free_tier_compute_guardrails.reference_tier",
    ).lower()
    if reference_tier_name != "starter":
        raise ValueError("free_tier_compute_guardrails.reference_tier must be starter")
    guardrail_limits = free_tier_compute_guardrails.get("limits")
    if not isinstance(guardrail_limits, list) or not guardrail_limits:
        raise ValueError("free_tier_compute_guardrails.limits must be a non-empty array")
    free_guardrails_bounded = True
    for idx, item in enumerate(guardrail_limits):
        if not isinstance(item, dict):
            raise ValueError(f"free_tier_compute_guardrails.limits[{idx}] must be an object")
        _parse_non_empty_str(
            item.get("limit_name"),
            field=f"free_tier_compute_guardrails.limits[{idx}].limit_name",
        )
        free_limit = _parse_int(
            item.get("free_limit"),
            field=f"free_tier_compute_guardrails.limits[{idx}].free_limit",
            min_value=0,
        )
        starter_limit = _parse_int(
            item.get("starter_limit"),
            field=f"free_tier_compute_guardrails.limits[{idx}].starter_limit",
            min_value=0,
        )
        expected_bounded = free_limit <= starter_limit
        actual_bounded = _parse_bool(
            item.get("free_le_starter"),
            field=f"free_tier_compute_guardrails.limits[{idx}].free_le_starter",
        )
        if actual_bounded != expected_bounded:
            raise ValueError(
                "free_tier_compute_guardrails.limits[{idx}].free_le_starter mismatch: "
                "expected {expected} got {actual}".format(
                    idx=idx,
                    expected=expected_bounded,
                    actual=actual_bounded,
                )
            )
        free_guardrails_bounded = free_guardrails_bounded and expected_bounded
    bounded_claim = _parse_bool(
        free_tier_compute_guardrails.get("bounded_against_starter"),
        field="free_tier_compute_guardrails.bounded_against_starter",
    )
    if bounded_claim != free_guardrails_bounded:
        raise ValueError(
            "free_tier_compute_guardrails.bounded_against_starter mismatch: "
            f"expected {free_guardrails_bounded}, got {bounded_claim}"
        )

    free_tier_margin_watch = payload.get("free_tier_margin_watch")
    if not isinstance(free_tier_margin_watch, dict):
        raise ValueError("free_tier_margin_watch must be an object")
    free_total_tenants = _parse_int(
        free_tier_margin_watch.get("free_total_tenants"),
        field="free_tier_margin_watch.free_total_tenants",
        min_value=0,
    )
    free_active_subscriptions = _parse_int(
        free_tier_margin_watch.get("free_active_subscriptions"),
        field="free_tier_margin_watch.free_active_subscriptions",
        min_value=0,
    )
    if free_total_tenants > 0 and free_active_subscriptions > free_total_tenants:
        raise ValueError(
            "free_tier_margin_watch.free_active_subscriptions cannot exceed free_total_tenants"
        )
    free_total_llm_cost_usd = _parse_float(
        free_tier_margin_watch.get("free_total_llm_cost_usd"),
        field="free_tier_margin_watch.free_total_llm_cost_usd",
        min_value=0.0,
    )
    _parse_float(
        free_tier_margin_watch.get("free_p95_tenant_monthly_cost_usd"),
        field="free_tier_margin_watch.free_p95_tenant_monthly_cost_usd",
        min_value=0.0,
    )
    starter_gross_mrr_usd = _parse_float(
        free_tier_margin_watch.get("starter_gross_mrr_usd"),
        field="free_tier_margin_watch.starter_gross_mrr_usd",
        min_value=0.0,
    )
    max_allowed_pct = _parse_float(
        free_tier_margin_watch.get("max_allowed_pct_of_starter_gross_mrr"),
        field="free_tier_margin_watch.max_allowed_pct_of_starter_gross_mrr",
        min_value=0.0,
    )
    ratio_raw = free_tier_margin_watch.get("free_llm_cost_pct_of_starter_gross_mrr")
    ratio_payload: float | None
    if ratio_raw is None:
        ratio_payload = None
    else:
        ratio_payload = _parse_float(
            ratio_raw,
            field="free_tier_margin_watch.free_llm_cost_pct_of_starter_gross_mrr",
            min_value=0.0,
        )
    if starter_gross_mrr_usd > 0.0:
        computed_ratio = (free_total_llm_cost_usd / starter_gross_mrr_usd) * 100.0
        if ratio_payload is None:
            raise ValueError(
                "free_tier_margin_watch.free_llm_cost_pct_of_starter_gross_mrr must be numeric when starter_gross_mrr_usd > 0"
            )
        if round(ratio_payload, 6) != round(computed_ratio, 6):
            raise ValueError(
                "free_tier_margin_watch.free_llm_cost_pct_of_starter_gross_mrr "
                "must match free_total_llm_cost_usd/starter_gross_mrr_usd ratio"
            )
        free_tier_margin_guarded = ratio_payload <= max_allowed_pct
    else:
        if free_total_llm_cost_usd > 0.0:
            if ratio_payload is not None:
                raise ValueError(
                    "free_tier_margin_watch.free_llm_cost_pct_of_starter_gross_mrr "
                    "must be null when starter_gross_mrr_usd=0 and free_total_llm_cost_usd>0"
                )
            free_tier_margin_guarded = False
        else:
            if ratio_payload is not None and round(ratio_payload, 6) != 0.0:
                raise ValueError(
                    "free_tier_margin_watch.free_llm_cost_pct_of_starter_gross_mrr "
                    "must be 0 or null when starter_gross_mrr_usd=0 and free_total_llm_cost_usd=0"
                )
            free_tier_margin_guarded = True

    gate_results = payload.get("gate_results")
    if not isinstance(gate_results, dict):
        raise ValueError("gate_results must be an object")
    expected_gate_results = {
        "telemetry_gate_required_tiers_present": required_tiers_present,
        "telemetry_gate_window_valid": window_valid,
        "telemetry_gate_percentiles_valid": percentiles_valid,
        "telemetry_gate_artifact_fresh": artifact_fresh,
        "telemetry_gate_free_tier_guardrails_bounded": free_guardrails_bounded,
        "telemetry_gate_free_tier_margin_guarded": free_tier_margin_guarded,
    }
    for key, expected in expected_gate_results.items():
        actual = _parse_bool(gate_results.get(key), field=f"gate_results.{key}")
        if actual != expected:
            raise ValueError(
                f"gate_results.{key} mismatch: expected {expected}, got {actual}"
            )

    print(
        "Finance telemetry snapshot verified: "
        f"{snapshot_path} (tiers={','.join(sorted(REQUIRED_TIERS))})"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate finance telemetry snapshot artifact."
    )
    parser.add_argument(
        "--snapshot-path",
        required=True,
        help="Path to finance telemetry snapshot JSON.",
    )
    parser.add_argument(
        "--max-artifact-age-hours",
        type=float,
        default=None,
        help="Optional max allowed age for artifact timestamp.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_snapshot(
        snapshot_path=Path(str(args.snapshot_path)),
        max_artifact_age_hours=(
            float(args.max_artifact_age_hours)
            if args.max_artifact_age_hours is not None
            else None
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
