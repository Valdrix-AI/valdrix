from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
OPS_EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"


def test_release_artifact_template_pack_exists_with_required_files() -> None:
    required_paths = [
        OPS_EVIDENCE_DIR / "README.md",
        OPS_EVIDENCE_DIR / "enforcement_stress_artifact_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "enforcement_failure_injection_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "finance_guardrails_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "finance_telemetry_snapshot_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "finance_committee_packet_assumptions_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "valdrix_disposition_register_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "pricing_benchmark_register_TEMPLATE.json",
        OPS_EVIDENCE_DIR / "pkg_fin_policy_decisions_TEMPLATE.json",
        REPO_ROOT / "docs" / "evidence" / "ci-green-template.md",
    ]
    for path in required_paths:
        assert path.exists(), str(path)


def test_release_artifact_template_pack_contains_required_contract_tokens() -> None:
    readme_raw = (OPS_EVIDENCE_DIR / "README.md").read_text(encoding="utf-8")
    stress_raw = (
        OPS_EVIDENCE_DIR / "enforcement_stress_artifact_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    failure_raw = (
        OPS_EVIDENCE_DIR / "enforcement_failure_injection_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    finance_raw = (OPS_EVIDENCE_DIR / "finance_guardrails_TEMPLATE.json").read_text(
        encoding="utf-8"
    )
    finance_telemetry_raw = (
        OPS_EVIDENCE_DIR / "finance_telemetry_snapshot_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    finance_assumptions_raw = (
        OPS_EVIDENCE_DIR / "finance_committee_packet_assumptions_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    valdrix_disposition_raw = (
        OPS_EVIDENCE_DIR / "valdrix_disposition_register_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    pricing_raw = (
        OPS_EVIDENCE_DIR / "pricing_benchmark_register_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    pkg_fin_raw = (
        OPS_EVIDENCE_DIR / "pkg_fin_policy_decisions_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    ci_raw = (REPO_ROOT / "docs" / "evidence" / "ci-green-template.md").read_text(
        encoding="utf-8"
    )

    assert "enforcement_stress_artifact_YYYY-MM-DD.json" in readme_raw
    assert "enforcement_failure_injection_YYYY-MM-DD.json" in readme_raw
    assert "finance_guardrails_YYYY-MM-DD.json" in readme_raw
    assert "finance_telemetry_snapshot_YYYY-MM-DD.json" in readme_raw
    assert "finance_committee_packet_assumptions_YYYY-MM-DD.json" in readme_raw
    assert "valdrix_disposition_register_YYYY-MM-DD.json" in readme_raw
    assert "pricing_benchmark_register_YYYY-MM-DD.json" in readme_raw
    assert "pkg_fin_policy_decisions_YYYY-MM-DD.json" in readme_raw

    assert '"profile": "enforcement"' in stress_raw
    assert '"runner": "scripts/load_test_api.py"' in stress_raw

    assert '"profile": "enforcement_failure_injection"' in failure_raw
    assert '"runner": "staged_failure_injection"' in failure_raw
    assert '"fin_gate_1_gross_margin_floor"' in finance_raw
    assert '"tier_unit_economics"' in finance_raw
    assert '"telemetry_gate_required_tiers_present"' in finance_telemetry_raw
    assert '"tier_llm_usage"' in finance_telemetry_raw
    assert '"free_tier_compute_guardrails"' in finance_telemetry_raw
    assert '"telemetry_gate_free_tier_margin_guarded"' in finance_telemetry_raw
    assert '"annual_mix_by_tier"' in finance_assumptions_raw
    assert '"scenario_models"' in finance_assumptions_raw
    assert '"finding_id"' in valdrix_disposition_raw
    assert '"review_by"' in valdrix_disposition_raw
    assert '"exit_criteria"' in valdrix_disposition_raw
    assert '"required_source_classes"' in pricing_raw
    assert '"pkg_gate_020_register_fresh"' in pricing_raw
    assert '"enterprise_pricing_model"' in pkg_fin_raw
    assert '"pkg_fin_gate_policy_decisions_complete"' in pkg_fin_raw
    assert '"source_type"' in pkg_fin_raw
    assert '"pricing_motion_allowed"' in pkg_fin_raw
    assert '"governance_mode"' in pkg_fin_raw
    assert '"decision_backlog"' in pkg_fin_raw
    assert '"required_decision_ids"' in pkg_fin_raw
    assert '"decision_items"' in pkg_fin_raw
    assert '"pkg_fin_gate_pricing_motion_guarded"' in pkg_fin_raw
    assert '"pkg_fin_gate_backlog_coverage_complete"' in pkg_fin_raw
    assert '"pkg_fin_gate_launch_blockers_resolved"' in pkg_fin_raw
    assert '"pkg_fin_gate_postlaunch_commitments_scheduled"' in pkg_fin_raw

    assert "Enterprise Gate Command" in ci_raw
    assert "coverage-enterprise-gate.xml" in ci_raw
