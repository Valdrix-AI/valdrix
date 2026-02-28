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
        OPS_EVIDENCE_DIR / "pricing_benchmark_register_TEMPLATE.json",
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
    pricing_raw = (
        OPS_EVIDENCE_DIR / "pricing_benchmark_register_TEMPLATE.json"
    ).read_text(encoding="utf-8")
    ci_raw = (REPO_ROOT / "docs" / "evidence" / "ci-green-template.md").read_text(
        encoding="utf-8"
    )

    assert "enforcement_stress_artifact_YYYY-MM-DD.json" in readme_raw
    assert "enforcement_failure_injection_YYYY-MM-DD.json" in readme_raw
    assert "finance_guardrails_YYYY-MM-DD.json" in readme_raw
    assert "pricing_benchmark_register_YYYY-MM-DD.json" in readme_raw

    assert '"profile": "enforcement"' in stress_raw
    assert '"runner": "scripts/load_test_api.py"' in stress_raw

    assert '"profile": "enforcement_failure_injection"' in failure_raw
    assert '"runner": "staged_failure_injection"' in failure_raw
    assert '"fin_gate_1_gross_margin_floor"' in finance_raw
    assert '"tier_unit_economics"' in finance_raw
    assert '"required_source_classes"' in pricing_raw
    assert '"pkg_gate_020_register_fresh"' in pricing_raw

    assert "Enterprise Gate Command" in ci_raw
    assert "coverage-enterprise-gate.xml" in ci_raw
