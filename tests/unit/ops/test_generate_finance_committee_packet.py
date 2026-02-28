from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_finance_committee_packet import main


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _telemetry_payload() -> dict[str, object]:
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
            {"tier": "starter", "total_tenants": 100, "active_subscriptions": 80, "dunning_events": 6},
            {"tier": "growth", "total_tenants": 70, "active_subscriptions": 50, "dunning_events": 5},
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
                "total_cost_usd": 1200.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 5.0, "p95": 16.0, "p99": 22.0},
            },
            {
                "tier": "growth",
                "total_cost_usd": 1600.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 8.0, "p95": 21.0, "p99": 31.0},
            },
            {
                "tier": "pro",
                "total_cost_usd": 2200.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 12.0, "p95": 32.0, "p99": 45.0},
            },
            {
                "tier": "enterprise",
                "total_cost_usd": 3200.0,
                "tenant_monthly_cost_percentiles_usd": {"p50": 18.0, "p95": 48.0, "p99": 70.0},
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


def _assumptions_payload() -> dict[str, object]:
    return {
        "captured_at": "2026-02-28T12:05:00Z",
        "thresholds": {
            "min_blended_gross_margin_percent": 55.0,
            "max_p95_tenant_llm_cogs_pct_mrr": 40.0,
            "max_annual_discount_impact_percent": 20.0,
            "min_growth_to_pro_conversion_mom_delta_percent": 0.0,
            "min_pro_to_enterprise_conversion_mom_delta_percent": 0.0,
            "min_stress_margin_percent": 50.0,
            "required_consecutive_margin_closes": 2,
        },
        "annual_mix_by_tier": {
            "starter": 0.7,
            "growth": 0.7,
            "pro": 0.7,
            "enterprise": 0.5,
        },
        "infra_cogs_percent_of_effective_mrr_by_tier": {
            "starter": 7.0,
            "growth": 7.0,
            "pro": 6.0,
            "enterprise": 5.0,
        },
        "support_cogs_per_active_subscription_usd_by_tier": {
            "starter": 5.0,
            "growth": 8.0,
            "pro": 12.0,
            "enterprise": 20.0,
        },
        "support_cogs_per_dunning_event_usd": 10.0,
        "conversion_signals": {
            "growth_to_pro_conversion_mom_delta_percent": 0.2,
            "pro_to_enterprise_conversion_mom_delta_percent": 0.1,
        },
        "stress_scenario": {"infra_cost_multiplier": 2.0},
        "close_history": [
            {"month": "2026-01", "blended_gross_margin_percent": 78.0}
        ],
        "scenario_models": {
            "price_sensitivity": [
                {
                    "name": "baseline",
                    "subscription_multipliers_by_tier": {
                        "starter": 1.0,
                        "growth": 1.0,
                        "pro": 1.0,
                        "enterprise": 1.0,
                    },
                    "monthly_price_multipliers_by_tier": {
                        "starter": 1.0,
                        "growth": 1.0,
                        "pro": 1.0,
                        "enterprise": 1.0,
                    },
                }
            ]
        },
        "self_hosted_tco_inputs": {
            "annual_staffing_usd": 250000.0,
            "annual_oncall_usd": 50000.0,
            "annual_security_compliance_usd": 40000.0,
            "annual_infra_ops_usd": 60000.0,
            "annual_tooling_usd": 30000.0,
        },
    }


def test_generate_finance_committee_packet_emits_expected_outputs(tmp_path: Path) -> None:
    telemetry = tmp_path / "telemetry.json"
    assumptions = tmp_path / "assumptions.json"
    output_dir = tmp_path / "output"
    _write(telemetry, _telemetry_payload())
    _write(assumptions, _assumptions_payload())

    assert (
        main(
            [
                "--telemetry-path",
                str(telemetry),
                "--assumptions-path",
                str(assumptions),
                "--output-dir",
                str(output_dir),
                "--require-all-gates-pass",
            ]
        )
        == 0
    )

    assert (output_dir / "finance_guardrails_2026-02.json").exists()
    assert (output_dir / "finance_committee_packet_2026-02.json").exists()
    assert (output_dir / "finance_committee_tier_unit_economics_2026-02.csv").exists()
    assert (output_dir / "finance_committee_scenarios_2026-02.csv").exists()


def test_generate_finance_committee_packet_returns_non_zero_when_gate_fails(
    tmp_path: Path,
) -> None:
    telemetry = tmp_path / "telemetry.json"
    assumptions = tmp_path / "assumptions.json"
    output_dir = tmp_path / "output"
    payload = _assumptions_payload()
    payload["thresholds"]["min_blended_gross_margin_percent"] = 99.0
    _write(telemetry, _telemetry_payload())
    _write(assumptions, payload)

    assert (
        main(
            [
                "--telemetry-path",
                str(telemetry),
                "--assumptions-path",
                str(assumptions),
                "--output-dir",
                str(output_dir),
                "--require-all-gates-pass",
            ]
        )
        == 2
    )


def test_generate_finance_committee_packet_sends_alert_when_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = tmp_path / "telemetry.json"
    assumptions = tmp_path / "assumptions.json"
    output_dir = tmp_path / "output"
    payload = _assumptions_payload()
    payload["thresholds"]["min_blended_gross_margin_percent"] = 99.0
    _write(telemetry, _telemetry_payload())
    _write(assumptions, payload)

    calls: list[str] = []

    class _Resp:
        status_code = 200

    def _mock_post(url: str, json: dict[str, object], timeout: float):  # type: ignore[override]
        del json, timeout
        calls.append(url)
        return _Resp()

    monkeypatch.setattr("scripts.generate_finance_committee_packet.httpx.post", _mock_post)

    exit_code = main(
        [
            "--telemetry-path",
            str(telemetry),
            "--assumptions-path",
            str(assumptions),
            "--output-dir",
            str(output_dir),
            "--alert-webhook-url",
            "https://alerts.example.test/hook",
        ]
    )
    assert exit_code == 0
    assert calls == ["https://alerts.example.test/hook"]
