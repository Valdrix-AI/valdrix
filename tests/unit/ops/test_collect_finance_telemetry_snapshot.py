from __future__ import annotations

from datetime import datetime, timezone

from scripts.collect_finance_telemetry_snapshot import (
    _build_snapshot_payload,
    _percentile,
)


def test_percentile_interpolation_is_deterministic() -> None:
    values = [1.0, 5.0, 9.0, 13.0]
    assert _percentile(values, 0.0) == 1.0
    assert _percentile(values, 50.0) == 7.0
    assert _percentile(values, 95.0) >= 12.0
    assert _percentile(values, 100.0) == 13.0


def test_build_snapshot_payload_populates_tier_revenue_and_gates() -> None:
    payload = _build_snapshot_payload(
        window_start=datetime(2026, 2, 1, tzinfo=timezone.utc),
        window_end_exclusive=datetime(2026, 3, 1, tzinfo=timezone.utc),
        label="2026-02",
        db_engine="postgresql",
        subscription_snapshot={
            "free": {"total_tenants": 200, "active_subscriptions": 160, "dunning_events": 0},
            "starter": {"total_tenants": 100, "active_subscriptions": 80, "dunning_events": 8},
            "growth": {"total_tenants": 80, "active_subscriptions": 60, "dunning_events": 5},
            "pro": {"total_tenants": 40, "active_subscriptions": 30, "dunning_events": 2},
            "enterprise": {"total_tenants": 20, "active_subscriptions": 15, "dunning_events": 1},
        },
        llm_snapshot={
            "free": {"total_cost_usd": 240.0, "p50": 1.2, "p95": 4.4, "p99": 7.2},
            "starter": {"total_cost_usd": 1100.0, "p50": 5.0, "p95": 12.0, "p99": 18.0},
            "growth": {"total_cost_usd": 1500.0, "p50": 8.0, "p95": 19.0, "p99": 26.0},
            "pro": {"total_cost_usd": 2300.0, "p50": 13.0, "p95": 32.0, "p99": 44.0},
            "enterprise": {"total_cost_usd": 3100.0, "p50": 20.0, "p95": 49.0, "p99": 66.0},
        },
    )

    assert payload["window"]["label"] == "2026-02"
    assert payload["runtime"]["database_engine"] == "postgresql"
    assert payload["gate_results"]["telemetry_gate_required_tiers_present"] is True
    assert payload["gate_results"]["telemetry_gate_free_tier_guardrails_bounded"] is True
    assert payload["gate_results"]["telemetry_gate_free_tier_margin_guarded"] is True
    assert payload["free_tier_compute_guardrails"]["tier"] == "free"
    assert payload["free_tier_compute_guardrails"]["bounded_against_starter"] is True
    assert payload["free_tier_margin_watch"]["free_active_subscriptions"] == 160

    revenues = {row["tier"]: row["gross_mrr_usd"] for row in payload["tier_revenue_inputs"]}
    assert revenues["free"] == 0.0
    assert revenues["starter"] > 0.0
    assert revenues["growth"] > revenues["starter"]
