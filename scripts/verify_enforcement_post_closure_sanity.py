"""Release-gate validator for enforcement post-closure sanity checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceToken:
    path: str
    token: str


DIMENSION_TOKENS: dict[str, tuple[EvidenceToken, ...]] = {
    "concurrency": (
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_property_and_concurrency.py",
            "test_concurrency_same_idempotency_key_dedupes_single_decision",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_property_and_concurrency.py",
            "test_concurrency_reconcile_overdue_claims_each_reservation_once",
        ),
    ),
    "observability": (
        EvidenceToken(
            "ops/alerts/enforcement_control_plane_rules.yml",
            "ValdrixEnforcementGateLockContentionSpike",
        ),
        EvidenceToken(
            "ops/alerts/enforcement_control_plane_rules.yml",
            "ValdrixEnforcementErrorBudgetBurnFast",
        ),
        EvidenceToken(
            "docs/ops/alert-evidence-2026-02-25.md",
            "Release Hold Criteria (BSAFE-016)",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_api.py",
            "test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes",
        ),
        EvidenceToken(
            "docs/runbooks/enforcement_preprovision_integrations.md",
            "valdrix_ops_enforcement_gate_lock_events_total",
        ),
    ),
    "deterministic_replay": (
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "test_consume_approval_token_rejects_replay",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "test_reconcile_reservation_idempotent_replay_with_same_key",
        ),
    ),
    "snapshot_stability": (
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "test_evaluate_gate_computed_context_snapshot_metadata_stable_across_runs",
        ),
        EvidenceToken(
            "app/modules/enforcement/domain/service.py",
            "computed_context_lineage_sha256",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "computed_context_month_start",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "computed_context_data_source_mode",
        ),
    ),
    "export_integrity": (
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_api.py",
            "test_enforcement_export_parity_and_archive_endpoints",
        ),
        EvidenceToken(
            "app/modules/enforcement/domain/service.py",
            "policy_lineage_sha256",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_service.py",
            "test_build_export_bundle_reconciles_counts_and_is_deterministic",
        ),
    ),
    "failure_modes": (
        EvidenceToken(
            "docs/ops/enforcement_failure_injection_matrix_2026-02-25.md",
            "FI-001",
        ),
        EvidenceToken(
            "docs/ops/enforcement_failure_injection_matrix_2026-02-25.md",
            "FI-005",
        ),
        EvidenceToken(
            "tests/unit/enforcement/test_enforcement_api.py",
            "test_gate_failsafe_timeout_and_error_modes",
        ),
    ),
    "operational_misconfiguration": (
        EvidenceToken(
            "tests/unit/ops/test_enforcement_webhook_helm_contract.py",
            "test_helm_webhook_rejects_fail_closed_without_ha_replicas",
        ),
        EvidenceToken(
            "tests/unit/ops/test_enforcement_webhook_helm_contract.py",
            "test_helm_webhook_rejects_fail_closed_with_recreate_strategy",
        ),
        EvidenceToken(
            "docs/runbooks/enforcement_preprovision_integrations.md",
            "failurePolicy: Fail",
        ),
    ),
}

DOC_REQUIRED_TOKENS: tuple[str, ...] = (
    "Whenever a control, feature, or gap is marked DONE",
    "concurrency",
    "observability",
    "deterministic replay",
    "snapshot stability",
    "export integrity",
    "failure modes",
    "operational misconfiguration risks",
    "release-critical",
)

GAP_REGISTER_REQUIRED_TOKENS: tuple[str, ...] = (
    "post-closure sanity check gate",
    "BSAFE-010",
    "BSAFE-015",
    "BSAFE-016",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def validate_tokens(tokens: tuple[EvidenceToken, ...], *, repo_root: Path) -> None:
    for entry in tokens:
        full_path = repo_root / entry.path
        raw = _read_text(full_path)
        if entry.token not in raw:
            raise ValueError(
                f"Missing token {entry.token!r} in required file {entry.path}"
            )


def validate_dimension_tokens(*, repo_root: Path) -> None:
    for dimension, tokens in DIMENSION_TOKENS.items():
        validate_tokens(tokens, repo_root=repo_root)
        print(f"[post-closure-sanity] {dimension}: OK ({len(tokens)} checks)")


def validate_doc_contract(*, doc_path: Path) -> None:
    raw = _read_text(doc_path)
    for token in DOC_REQUIRED_TOKENS:
        if token not in raw:
            raise ValueError(
                f"Post-closure sanity doc missing required token: {token!r}"
            )


def validate_gap_register_contract(*, gap_register_path: Path) -> None:
    raw = _read_text(gap_register_path)
    for token in GAP_REGISTER_REQUIRED_TOKENS:
        if token not in raw:
            raise ValueError(f"Gap register missing required token: {token!r}")


def verify_post_closure_sanity(
    *,
    doc_path: Path,
    gap_register_path: Path,
    repo_root: Path,
) -> int:
    validate_dimension_tokens(repo_root=repo_root)
    validate_doc_contract(doc_path=doc_path)
    validate_gap_register_contract(gap_register_path=gap_register_path)
    print(
        "Enforcement post-closure sanity checks verified "
        f"(dimensions={len(DIMENSION_TOKENS)})."
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate post-closure sanity checks for enforcement controls."
    )
    parser.add_argument(
        "--doc-path",
        default="docs/ops/enforcement_post_closure_sanity_2026-02-26.md",
        help="Post-closure sanity policy document path.",
    )
    parser.add_argument(
        "--gap-register",
        default="docs/ops/enforcement_control_plane_gap_register_2026-02-23.md",
        help="Gap register path that must include post-closure sanity closure evidence.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    return verify_post_closure_sanity(
        doc_path=repo_root / str(args.doc_path),
        gap_register_path=repo_root / str(args.gap_register),
        repo_root=repo_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
