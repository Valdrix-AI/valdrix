from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"
README_PATH = EVIDENCE_DIR / "README.md"


def test_finance_telemetry_pack_artifacts_exist() -> None:
    required = (
        EVIDENCE_DIR / "finance_telemetry_snapshot_TEMPLATE.json",
        EVIDENCE_DIR / "finance_telemetry_snapshot_2026-02-28.json",
        EVIDENCE_DIR / "finance_committee_packet_assumptions_TEMPLATE.json",
        EVIDENCE_DIR / "finance_committee_packet_assumptions_2026-02-28.json",
        REPO_ROOT / "scripts" / "collect_finance_telemetry_snapshot.py",
        REPO_ROOT / "scripts" / "verify_finance_telemetry_snapshot.py",
        REPO_ROOT / "scripts" / "generate_finance_committee_packet.py",
    )
    for path in required:
        assert path.exists(), f"missing required finance telemetry artifact: {path}"


def test_finance_telemetry_readme_contract_entries_present() -> None:
    readme_raw = README_PATH.read_text(encoding="utf-8")
    assert "finance_telemetry_snapshot_YYYY-MM-DD.json" in readme_raw
    assert "finance_committee_packet_assumptions_YYYY-MM-DD.json" in readme_raw
    assert "scripts/verify_finance_telemetry_snapshot.py" in readme_raw
    assert "scripts/generate_finance_committee_packet.py" in readme_raw
