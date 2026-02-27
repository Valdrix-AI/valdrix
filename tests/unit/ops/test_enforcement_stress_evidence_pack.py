from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = REPO_ROOT / "docs" / "ops" / "enforcement_stress_evidence_2026-02-25.md"


def test_enforcement_stress_evidence_protocol_exists_and_references_gate_tools() -> None:
    assert DOC_PATH.exists()
    raw = DOC_PATH.read_text(encoding="utf-8")

    required_snippets = [
        "scripts/load_test_api.py",
        "--profile enforcement",
        "--rounds 3",
        "scripts/verify_enforcement_stress_evidence.py",
        "--max-p95-seconds 2.0",
        "--max-error-rate-percent 1.0",
        "--min-throughput-rps 0.5",
        "Failing stress evidence blocks release promotion",
    ]
    for snippet in required_snippets:
        assert snippet in raw
