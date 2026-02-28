from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"
MEMO_PATH = REPO_ROOT / "docs" / "ops" / "pkg_fin_decision_memo_2026-02-27.md"


def test_finance_guardrails_evidence_artifacts_exist() -> None:
    required_paths = [
        EVIDENCE_DIR / "finance_guardrails_TEMPLATE.json",
        EVIDENCE_DIR / "finance_guardrails_2026-02-27.json",
        REPO_ROOT / "scripts" / "verify_finance_guardrails_evidence.py",
        MEMO_PATH,
    ]
    for path in required_paths:
        assert path.exists(), str(path)


def test_finance_guardrails_memo_and_readme_include_required_contracts() -> None:
    readme_raw = (EVIDENCE_DIR / "README.md").read_text(encoding="utf-8")
    memo_raw = MEMO_PATH.read_text(encoding="utf-8")

    assert "finance_guardrails_YYYY-MM-DD.json" in readme_raw
    assert "scripts/verify_finance_guardrails_evidence.py" in readme_raw
    assert "--max-artifact-age-hours 744" in readme_raw

    assert "internal telemetry" in memo_raw
    assert "policy choices" in memo_raw
    assert "FinOps Framework capabilities" in memo_raw
    assert "Stripe subscription price-change operations" in memo_raw
