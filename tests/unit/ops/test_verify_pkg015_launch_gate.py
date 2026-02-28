from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_pkg015_launch_gate import main, verify_pkg015_launch_gate


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _gap_register_payload(*, ecp004_status: str = "DONE", include_doc_tokens: bool = True) -> str:
    header = [
        "# Enforcement Control Plane Gap Register",
        "## Recommended decision gate",
    ]
    if include_doc_tokens:
        header.extend(
            [
                "`PKG-015`",
                "Use analytics-led messaging before gate closure.",
                "Use economic-control-plane messaging after gate closure.",
            ]
        )
    table = [
        "| ID | Priority | Status | Required | Notes |",
        "|---|---|---|---|---|",
        "| ECP-002 | P0 | DONE | Yes | Entitlement waterfall |",
        "| ECP-003 | P0 | DONE | Yes | Approval routing |",
        f"| ECP-004 | P0 | {ecp004_status} | Yes | Credit lifecycle |",
        "| ECP-005 | P0 | DONE | Yes | Fail-mode controls |",
        "| ECP-012 | P0 | DONE | Yes | Concurrency safety |",
        "| PKG-003 | P0 | DONE | Yes | Tier gates |",
        "| PKG-006 | P0 | DONE | Yes | Enforceability matrix |",
        "| PKG-007 | P0 | DONE | Yes | Curated enterprise entitlements |",
    ]
    return "\n".join([*header, *table]) + "\n"


def _matrix_payload(*, policy_configuration_status: str = "runtime_gated") -> dict[str, object]:
    return {
        "captured_at": "2026-02-28T12:00:00Z",
        "features": {
            "auto_remediation": {"status": "runtime_gated", "evidence": ["app/shared/core/pricing.py"]},
            "api_access": {"status": "runtime_gated", "evidence": ["app/shared/core/pricing.py"]},
            "policy_configuration": {
                "status": policy_configuration_status,
                "evidence": ["app/shared/core/pricing.py"],
            },
            "escalation_workflow": {
                "status": "runtime_gated",
                "evidence": ["app/shared/core/pricing.py"],
            },
            "incident_integrations": {
                "status": "runtime_gated",
                "evidence": ["app/shared/core/pricing.py"],
            },
        },
    }


def test_verify_pkg015_launch_gate_accepts_valid_inputs(tmp_path: Path) -> None:
    gap_path = tmp_path / "gap.md"
    matrix_path = tmp_path / "matrix.json"
    _write(gap_path, _gap_register_payload())
    matrix_path.write_text(json.dumps(_matrix_payload()), encoding="utf-8")

    assert (
        verify_pkg015_launch_gate(
            gap_register_path=gap_path,
            matrix_path=matrix_path,
        )
        == 0
    )


def test_verify_pkg015_launch_gate_rejects_not_done_required_item(tmp_path: Path) -> None:
    gap_path = tmp_path / "gap.md"
    matrix_path = tmp_path / "matrix.json"
    _write(gap_path, _gap_register_payload(ecp004_status="IN_PROGRESS"))
    matrix_path.write_text(json.dumps(_matrix_payload()), encoding="utf-8")

    with pytest.raises(ValueError, match="required items not DONE"):
        verify_pkg015_launch_gate(
            gap_register_path=gap_path,
            matrix_path=matrix_path,
        )


def test_verify_pkg015_launch_gate_rejects_missing_documentation_tokens(
    tmp_path: Path,
) -> None:
    gap_path = tmp_path / "gap.md"
    matrix_path = tmp_path / "matrix.json"
    _write(gap_path, _gap_register_payload(include_doc_tokens=False))
    matrix_path.write_text(json.dumps(_matrix_payload()), encoding="utf-8")

    with pytest.raises(ValueError, match="missing PKG-015 documentation token"):
        verify_pkg015_launch_gate(
            gap_register_path=gap_path,
            matrix_path=matrix_path,
        )


def test_verify_pkg015_launch_gate_rejects_non_runtime_gated_features(
    tmp_path: Path,
) -> None:
    gap_path = tmp_path / "gap.md"
    matrix_path = tmp_path / "matrix.json"
    _write(gap_path, _gap_register_payload())
    matrix_path.write_text(
        json.dumps(_matrix_payload(policy_configuration_status="catalog_only")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be runtime_gated"):
        verify_pkg015_launch_gate(
            gap_register_path=gap_path,
            matrix_path=matrix_path,
        )


def test_main_accepts_valid_inputs(tmp_path: Path) -> None:
    gap_path = tmp_path / "gap.md"
    matrix_path = tmp_path / "matrix.json"
    _write(gap_path, _gap_register_payload())
    matrix_path.write_text(json.dumps(_matrix_payload()), encoding="utf-8")

    assert (
        main(
            [
                "--gap-register",
                str(gap_path),
                "--matrix-path",
                str(matrix_path),
            ]
        )
        == 0
    )
