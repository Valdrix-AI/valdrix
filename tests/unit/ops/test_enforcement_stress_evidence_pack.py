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
        "--enforce-thresholds",
        "--out docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json",
        "docs/ops/evidence/enforcement_stress_artifact_TEMPLATE.json",
        "scripts/verify_enforcement_stress_evidence.py",
        "--evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json",
        "--min-duration-seconds 30",
        "--min-concurrent-users 10",
        "--required-database-engine postgresql",
        "--max-p95-seconds 2.0",
        "--max-error-rate-percent 1.0",
        "--min-throughput-rps 0.5",
        "evaluation.overall_meets_targets=true",
        "duration_seconds >= 30",
        "concurrent_users >= 10",
        "/api/v1/enforcement/exports/parity?limit=50",
        "thresholds.max_p95_seconds == verifier --max-p95-seconds",
        "evaluation.worst_p95_seconds == results.p95_response_time",
        "len(evaluation.rounds) == rounds",
        "Failing stress evidence blocks release promotion",
        "ENFORCEMENT_STRESS_EVIDENCE_PATH",
        "ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS",
        "ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS",
        "ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS",
        "ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE",
        "ENFORCEMENT_STRESS_EVIDENCE_REQUIRED",
        "scripts/run_enterprise_tdd_gate.py",
        "scripts/run_enforcement_release_evidence_gate.py",
        "--failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json",
        "--stress-required-database-engine postgresql",
    ]
    for snippet in required_snippets:
        assert snippet in raw
