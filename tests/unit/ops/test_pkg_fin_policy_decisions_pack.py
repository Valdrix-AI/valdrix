from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"
MEMO_PATH = REPO_ROOT / "docs" / "ops" / "pkg_fin_decision_memo_2026-02-27.md"


def test_pkg_fin_policy_decisions_artifacts_exist() -> None:
    required_paths = [
        EVIDENCE_DIR / "pkg_fin_policy_decisions_TEMPLATE.json",
        EVIDENCE_DIR / "pkg_fin_policy_decisions_2026-02-28.json",
        REPO_ROOT / "scripts" / "verify_pkg_fin_policy_decisions.py",
        MEMO_PATH,
    ]
    for path in required_paths:
        assert path.exists(), str(path)


def test_pkg_fin_policy_decisions_docs_include_required_contracts() -> None:
    readme_raw = (EVIDENCE_DIR / "README.md").read_text(encoding="utf-8")
    memo_raw = MEMO_PATH.read_text(encoding="utf-8")

    assert "pkg_fin_policy_decisions_YYYY-MM-DD.json" in readme_raw
    assert "scripts/verify_pkg_fin_policy_decisions.py" in readme_raw
    assert "--max-artifact-age-hours 744" in readme_raw
    assert "telemetry.source_type" in readme_raw
    assert "policy_decisions.pricing_motion_allowed" in readme_raw
    assert "approvals.governance_mode" in readme_raw
    assert "decision_backlog.required_decision_ids" in readme_raw
    assert "pkg_fin_gate_backlog_coverage_complete" in readme_raw
    assert "pkg_fin_gate_launch_blockers_resolved" in readme_raw
    assert "pkg_fin_gate_postlaunch_commitments_scheduled" in readme_raw

    assert "internal telemetry" in memo_raw
    assert "policy choices" in memo_raw
    assert "How to resolve the blocker" in memo_raw
