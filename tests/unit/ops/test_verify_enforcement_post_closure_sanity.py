from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_enforcement_post_closure_sanity import (
    ARTIFACT_TEMPLATE_TOKENS,
    DIMENSION_TOKENS,
    EvidenceToken,
    GAP_REGISTER_REQUIRED_TOKENS,
    validate_tokens,
    verify_post_closure_sanity,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_validate_tokens_fails_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        validate_tokens(
            (EvidenceToken("missing.txt", "token"),),
            repo_root=tmp_path,
        )


def test_validate_tokens_fails_for_missing_token(tmp_path: Path) -> None:
    payload = tmp_path / "sample.txt"
    payload.write_text("hello-world", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing token"):
        validate_tokens(
            (EvidenceToken("sample.txt", "nope"),),
            repo_root=tmp_path,
        )


def test_verify_post_closure_sanity_passes_against_repo_contracts() -> None:
    exit_code = verify_post_closure_sanity(
        doc_path=REPO_ROOT / "docs/ops/enforcement_post_closure_sanity_2026-02-26.md",
        gap_register_path=REPO_ROOT
        / "docs/ops/enforcement_control_plane_gap_register_2026-02-23.md",
        repo_root=REPO_ROOT,
    )
    assert exit_code == 0


def test_dimension_tokens_include_lock_contention_and_snapshot_export_evidence() -> None:
    observability = {(t.path, t.token) for t in DIMENSION_TOKENS["observability"]}
    deterministic = {(t.path, t.token) for t in DIMENSION_TOKENS["deterministic_replay"]}
    snapshot = {(t.path, t.token) for t in DIMENSION_TOKENS["snapshot_stability"]}
    export_integrity = {(t.path, t.token) for t in DIMENSION_TOKENS["export_integrity"]}

    assert (
        "tests/unit/enforcement/test_enforcement_api.py",
        "test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes",
    ) in observability
    assert (
        "docs/runbooks/enforcement_preprovision_integrations.md",
        "valdrics_ops_enforcement_gate_lock_events_total",
    ) in observability
    assert (
        "docs/ops/key-rotation-drill-2026-02-27.md",
        "rollback_validation_passed: true",
    ) in deterministic
    assert (
        "tests/unit/enforcement/test_enforcement_service.py",
        "computed_context_month_start",
    ) in snapshot
    assert (
        "tests/unit/enforcement/test_enforcement_service.py",
        "computed_context_data_source_mode",
    ) in snapshot
    assert (
        "tests/unit/enforcement/test_enforcement_service.py",
        "test_build_export_bundle_reconciles_counts_and_is_deterministic",
    ) in export_integrity


def test_artifact_template_contract_tokens_cover_release_packet_templates() -> None:
    artifact_tokens = {(entry.path, entry.token) for entry in ARTIFACT_TEMPLATE_TOKENS}
    assert (
        "docs/ops/evidence/enforcement_stress_artifact_TEMPLATE.json",
        '"profile": "enforcement"',
    ) in artifact_tokens
    assert (
        "docs/ops/evidence/enforcement_failure_injection_TEMPLATE.json",
        '"profile": "enforcement_failure_injection"',
    ) in artifact_tokens
    assert (
        "docs/evidence/ci-green-template.md",
        "coverage-enterprise-gate.xml",
    ) in artifact_tokens


def test_gap_register_required_tokens_include_canonical_open_items_header() -> None:
    required = set(GAP_REGISTER_REQUIRED_TOKENS)
    assert "Current Open Items (Canonical, 2026-02-27)" in required
    assert "CI-EVID-001" in required
    assert "BENCH-DOC-001" in required
