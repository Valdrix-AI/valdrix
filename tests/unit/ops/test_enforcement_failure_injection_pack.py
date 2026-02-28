from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = (
    REPO_ROOT / "docs" / "ops" / "enforcement_failure_injection_matrix_2026-02-25.md"
)


def test_failure_injection_pack_contains_required_scenarios_and_references() -> None:
    assert PACK_PATH.exists()
    raw = PACK_PATH.read_text(encoding="utf-8")

    required_scenarios = ["FI-001", "FI-002", "FI-003", "FI-004", "FI-005"]
    for scenario in required_scenarios:
        assert scenario in raw

    required_test_references = [
        "tests/unit/enforcement/test_enforcement_api.py::test_gate_failsafe_timeout_and_error_modes",
        "tests/unit/enforcement/test_enforcement_service.py::test_resolve_fail_safe_gate_timeout_mode_behavior",
        "tests/unit/enforcement/test_enforcement_api.py::test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes",
        "tests/unit/enforcement/test_enforcement_service_helpers.py::test_acquire_gate_evaluation_lock_rowcount_zero_raises_contended_reason",
        "tests/unit/enforcement/test_enforcement_api.py::test_consume_approval_token_endpoint_rejects_replay_and_tamper",
        "tests/unit/enforcement/test_enforcement_service.py::test_consume_approval_token_rejects_replay",
        "tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_same_idempotency_key_settles_credit_once",
        "tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_overdue_claims_each_reservation_once",
        "tests/unit/core/test_rate_limit.py::test_global_rate_limit_throttles_cross_tenant_requests",
        "tests/unit/enforcement/test_enforcement_api.py::test_enforcement_global_gate_limit_uses_configured_cap",
    ]
    for reference in required_test_references:
        assert reference in raw

    required_files = [
        "tests/unit/enforcement/test_enforcement_api.py",
        "tests/unit/enforcement/test_enforcement_service.py",
        "tests/unit/enforcement/test_enforcement_service_helpers.py",
        "tests/unit/enforcement/test_enforcement_property_and_concurrency.py",
        "tests/unit/core/test_rate_limit.py",
    ]
    for rel_path in required_files:
        assert (REPO_ROOT / rel_path).exists(), rel_path


def test_failure_injection_pack_documents_staged_artifact_contract() -> None:
    raw = PACK_PATH.read_text(encoding="utf-8")
    required_tokens = [
        "profile=enforcement_failure_injection",
        "runner=staged_failure_injection",
        "execution_class=staged",
        "executed_by != approved_by",
        "docs/ops/evidence/enforcement_failure_injection_TEMPLATE.json",
        "scripts/verify_enforcement_failure_injection_evidence.py",
        "scripts/run_enforcement_release_evidence_gate.py",
        "--stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json",
        "--stress-required-database-engine postgresql",
        "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH",
        "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS",
        "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED",
    ]
    for token in required_tokens:
        assert token in raw
