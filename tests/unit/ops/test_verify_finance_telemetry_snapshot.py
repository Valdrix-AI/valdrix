from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_finance_telemetry_snapshot import main, verify_snapshot


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_payload() -> dict[str, object]:
    return {
        "captured_at": "2026-02-28T12:00:00Z",
        "window": {
            "start": "2026-02-01T00:00:00Z",
            "end": "2026-02-27T23:59:59Z",
            "label": "2026-02",
        },
        "runtime": {
            "database_engine": "postgresql",
            "collector": "scripts/collect_finance_telemetry_snapshot.py",
        },
        "pricing_reference": {
            "free": {
                "monthly_price_usd": 0.0,
                "annual_price_usd": 0.0,
                "annual_monthly_factor": 0.0,
            },
            "starter": {
                "monthly_price_usd": 49.0,
                "annual_price_usd": 490.0,
                "annual_monthly_factor": 490.0 / (49.0 * 12.0),
            },
            "growth": {
                "monthly_price_usd": 149.0,
                "annual_price_usd": 1490.0,
                "annual_monthly_factor": 1490.0 / (149.0 * 12.0),
            },
            "pro": {
                "monthly_price_usd": 299.0,
                "annual_price_usd": 2990.0,
                "annual_monthly_factor": 2990.0 / (299.0 * 12.0),
            },
            "enterprise": {
                "monthly_price_usd": 799.0,
                "annual_price_usd": 7990.0,
                "annual_monthly_factor": 7990.0 / (799.0 * 12.0),
            },
        },
        "tier_subscription_snapshot": [
            {"tier": "free", "total_tenants": 220, "active_subscriptions": 180, "dunning_events": 0},
            {"tier": "starter", "total_tenants": 100, "active_subscriptions": 80, "dunning_events": 9},
            {"tier": "growth", "total_tenants": 70, "active_subscriptions": 55, "dunning_events": 6},
            {"tier": "pro", "total_tenants": 40, "active_subscriptions": 30, "dunning_events": 2},
            {"tier": "enterprise", "total_tenants": 20, "active_subscriptions": 15, "dunning_events": 1},
        ],
        "tier_llm_usage": [
            {
                "tier": "free",
                "total_cost_usd": 260.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 1.3, "p95": 4.0, "p99": 6.2},
            },
            {
                "tier": "starter",
                "total_cost_usd": 2000.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 8.0, "p95": 25.0, "p99": 36.0},
            },
            {
                "tier": "growth",
                "total_cost_usd": 2500.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 11.0, "p95": 35.0, "p99": 52.0},
            },
            {
                "tier": "pro",
                "total_cost_usd": 3100.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 21.0, "p95": 63.0, "p99": 90.0},
            },
            {
                "tier": "enterprise",
                "total_cost_usd": 4700.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 41.0, "p95": 120.0, "p99": 180.0},
            },
        ],
        "free_tier_compute_guardrails": {
            "tier": "free",
            "reference_tier": "starter",
            "limits": [
                {
                    "limit_name": "llm_analyses_per_day",
                    "free_limit": 1,
                    "starter_limit": 5,
                    "free_le_starter": True,
                },
                {
                    "limit_name": "llm_analyses_per_user_per_day",
                    "free_limit": 1,
                    "starter_limit": 2,
                    "free_le_starter": True,
                },
            ],
            "bounded_against_starter": True,
        },
        "free_tier_margin_watch": {
            "free_total_tenants": 220,
            "free_active_subscriptions": 180,
            "free_total_llm_cost_usd": 260.0,
            "free_p95_tenant_monthly_cost_usd": 4.0,
            "starter_gross_mrr_usd": 3920.0,
            "free_llm_cost_pct_of_starter_gross_mrr": (260.0 / 3920.0) * 100.0,
            "max_allowed_pct_of_starter_gross_mrr": 100.0,
        },
        "gate_results": {
            "telemetry_gate_required_tiers_present": True,
            "telemetry_gate_window_valid": True,
            "telemetry_gate_percentiles_valid": True,
            "telemetry_gate_artifact_fresh": True,
            "telemetry_gate_free_tier_guardrails_bounded": True,
            "telemetry_gate_free_tier_margin_guarded": True,
        },
    }


def test_verify_finance_telemetry_snapshot_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.json"
    _write(path, _valid_payload())
    assert verify_snapshot(snapshot_path=path) == 0


def test_verify_finance_telemetry_snapshot_rejects_missing_required_tier(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["tier_subscription_snapshot"] = payload["tier_subscription_snapshot"][:3]
    path = tmp_path / "telemetry.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required tiers"):
        verify_snapshot(snapshot_path=path)


def test_verify_finance_telemetry_snapshot_rejects_percentile_order(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    starter_row = next(row for row in payload["tier_llm_usage"] if row["tier"] == "starter")
    starter_row["tenant_monthly_cost_percentiles_usd"]["p95"] = 6.0
    path = tmp_path / "telemetry.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="percentiles must satisfy p50 <= p95 <= p99"):
        verify_snapshot(snapshot_path=path)


def test_verify_finance_telemetry_snapshot_rejects_gate_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["gate_results"]["telemetry_gate_window_valid"] = False
    path = tmp_path / "telemetry.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="gate_results.telemetry_gate_window_valid mismatch"):
        verify_snapshot(snapshot_path=path)


def test_verify_finance_telemetry_snapshot_rejects_free_guardrail_mismatch(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["free_tier_compute_guardrails"]["limits"][0]["free_limit"] = 7
    path = tmp_path / "telemetry.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="free_le_starter mismatch"):
        verify_snapshot(snapshot_path=path)


def test_verify_finance_telemetry_snapshot_rejects_too_old_artifact(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["captured_at"] = "2025-01-01T00:00:00Z"
    path = tmp_path / "telemetry.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="too old"):
        verify_snapshot(snapshot_path=path, max_artifact_age_hours=0.01)


def test_main_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.json"
    _write(path, _valid_payload())
    assert main(["--snapshot-path", str(path)]) == 0
