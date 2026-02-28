from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_finance_guardrails_evidence import main, verify_evidence


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_payload() -> dict[str, object]:
    return {
        "captured_at": "2026-02-27T10:00:00Z",
        "window": {
            "start": "2026-02-01T00:00:00Z",
            "end": "2026-02-27T23:59:59Z",
            "label": "2026-02",
        },
        "metrics": {
            "blended_gross_margin_percent": 84.6,
            "p95_tenant_llm_cogs_pct_mrr": 5.2,
            "annual_discount_impact_percent": 7.38,
            "growth_to_pro_conversion_mom_delta_percent": 0.8,
            "pro_to_enterprise_conversion_mom_delta_percent": 0.4,
            "stress_margin_percent": 76.0,
        },
        "thresholds": {
            "min_blended_gross_margin_percent": 80.0,
            "max_p95_tenant_llm_cogs_pct_mrr": 8.0,
            "max_annual_discount_impact_percent": 18.0,
            "min_growth_to_pro_conversion_mom_delta_percent": 0.0,
            "min_pro_to_enterprise_conversion_mom_delta_percent": 0.0,
            "min_stress_margin_percent": 75.0,
            "required_consecutive_margin_closes": 2,
        },
        "close_history": [
            {"month": "2026-01", "blended_gross_margin_percent": 84.2},
            {"month": "2026-02", "blended_gross_margin_percent": 84.6},
        ],
        "tier_unit_economics": [
            {
                "tier": "starter",
                "mrr_usd": 60000.0,
                "effective_mrr_usd": 55000.0,
                "llm_cogs_usd": 2000.0,
                "infra_cogs_usd": 5000.0,
                "support_cogs_usd": 1500.0,
                "gross_margin_percent": 84.55,
            },
            {
                "tier": "growth",
                "mrr_usd": 120000.0,
                "effective_mrr_usd": 110000.0,
                "llm_cogs_usd": 4000.0,
                "infra_cogs_usd": 9000.0,
                "support_cogs_usd": 2500.0,
                "gross_margin_percent": 85.91,
            },
            {
                "tier": "pro",
                "mrr_usd": 180000.0,
                "effective_mrr_usd": 165000.0,
                "llm_cogs_usd": 7000.0,
                "infra_cogs_usd": 15000.0,
                "support_cogs_usd": 4000.0,
                "gross_margin_percent": 84.24,
            },
            {
                "tier": "enterprise",
                "mrr_usd": 250000.0,
                "effective_mrr_usd": 235000.0,
                "llm_cogs_usd": 10000.0,
                "infra_cogs_usd": 20000.0,
                "support_cogs_usd": 7000.0,
                "gross_margin_percent": 84.26,
            },
        ],
        "stress_scenario": {
            "infra_cost_multiplier": 2.0,
            "projected_margin_percent": 76.0,
        },
        "gate_results": {
            "fin_gate_1_gross_margin_floor": True,
            "fin_gate_2_llm_cogs_containment": True,
            "fin_gate_3_annual_discount_impact": True,
            "fin_gate_4_expansion_signal": True,
            "fin_gate_5_stress_resilience": True,
        },
    }


def test_verify_finance_guardrails_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "finance.json"
    _write(path, _valid_payload())
    assert verify_evidence(evidence_path=path) == 0


def test_verify_finance_guardrails_rejects_gate_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["gate_results"]["fin_gate_2_llm_cogs_containment"] = False
    path = tmp_path / "finance.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="gate_results.fin_gate_2_llm_cogs_containment mismatch"):
        verify_evidence(evidence_path=path)


def test_verify_finance_guardrails_rejects_tier_contract_drift(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["tier_unit_economics"][0]["gross_margin_percent"] = 70.0
    path = tmp_path / "finance.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="gross_margin_percent must match computed margin"):
        verify_evidence(evidence_path=path)


def test_verify_finance_guardrails_rejects_discount_metric_drift(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["metrics"]["annual_discount_impact_percent"] = 12.0
    path = tmp_path / "finance.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="annual_discount_impact_percent must match computed impact"):
        verify_evidence(evidence_path=path)


def test_verify_finance_guardrails_rejects_missing_required_tier(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["tier_unit_economics"] = payload["tier_unit_economics"][:3]
    path = tmp_path / "finance.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required tiers"):
        verify_evidence(evidence_path=path)


def test_verify_finance_guardrails_rejects_too_old_artifact(tmp_path: Path) -> None:
    path = tmp_path / "finance.json"
    _write(path, _valid_payload())
    with pytest.raises(ValueError, match="too old"):
        verify_evidence(evidence_path=path, max_artifact_age_hours=0.01)


def test_main_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "finance.json"
    _write(path, _valid_payload())
    assert main(["--evidence-path", str(path)]) == 0
