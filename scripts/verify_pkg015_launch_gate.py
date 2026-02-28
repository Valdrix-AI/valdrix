#!/usr/bin/env python3
"""Verify PKG-015 B-launch readiness gate criteria."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_GAP_ITEMS: tuple[str, ...] = (
    "ECP-002",
    "ECP-003",
    "ECP-004",
    "ECP-005",
    "ECP-012",
    "PKG-003",
    "PKG-006",
    "PKG-007",
)
REQUIRED_DOC_TOKENS: tuple[str, ...] = (
    "PKG-015",
    "analytics-led",
    "economic-control-plane",
    "Recommended decision gate",
)
REQUIRED_RUNTIME_GATED_FEATURES: tuple[str, ...] = (
    "auto_remediation",
    "api_access",
    "policy_configuration",
    "escalation_workflow",
    "incident_integrations",
)

_TABLE_ROW_RE = re.compile(r"^\|\s*([A-Z]+-\d{3})\s*\|\s*[^|]+\|\s*([A-Z_]+)\s*\|")
_NARRATIVE_STATUS_RE = re.compile(
    r"`([A-Z]+-\d{3})`\s*\(`([A-Z_]+)`(?:[^)]*)\)",
    flags=re.IGNORECASE,
)


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _parse_gap_statuses(raw: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        table_match = _TABLE_ROW_RE.match(stripped)
        if table_match:
            item_id, status = table_match.groups()
            statuses[item_id] = status.strip().upper()
            continue
        for narrative_match in _NARRATIVE_STATUS_RE.finditer(stripped):
            item_id, status = narrative_match.groups()
            statuses[item_id.strip().upper()] = status.strip().upper()
    return statuses


def _verify_required_item_statuses(statuses: dict[str, str]) -> None:
    missing = [item_id for item_id in REQUIRED_GAP_ITEMS if item_id not in statuses]
    if missing:
        raise ValueError(f"Gap register missing required PKG-015 items: {missing}")
    not_done = [item_id for item_id in REQUIRED_GAP_ITEMS if statuses[item_id] != "DONE"]
    if not_done:
        raise ValueError(f"PKG-015 launch gate blocked; required items not DONE: {not_done}")


def _load_matrix(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Feature enforceability matrix does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Feature enforceability matrix payload must be an object")
    return payload


def _verify_runtime_gated_features(matrix_payload: dict[str, Any]) -> None:
    features = matrix_payload.get("features")
    if not isinstance(features, dict):
        raise ValueError("Feature enforceability matrix must contain features object")
    missing: list[str] = []
    not_runtime_gated: list[str] = []
    for feature in REQUIRED_RUNTIME_GATED_FEATURES:
        feature_payload = features.get(feature)
        if not isinstance(feature_payload, dict):
            missing.append(feature)
            continue
        status = str(feature_payload.get("status", "")).strip().lower()
        if status != "runtime_gated":
            not_runtime_gated.append(feature)
    if missing:
        raise ValueError(
            "Feature enforceability matrix missing required control-plane features: "
            f"{missing}"
        )
    if not_runtime_gated:
        raise ValueError(
            "PKG-015 launch gate blocked; control-plane features must be runtime_gated: "
            f"{not_runtime_gated}"
        )


def verify_pkg015_launch_gate(
    *,
    gap_register_path: Path,
    matrix_path: Path,
) -> int:
    gap_raw = _read_text(gap_register_path)
    for token in REQUIRED_DOC_TOKENS:
        if token not in gap_raw:
            raise ValueError(f"Gap register missing PKG-015 documentation token: {token!r}")

    statuses = _parse_gap_statuses(gap_raw)
    _verify_required_item_statuses(statuses)
    _verify_runtime_gated_features(_load_matrix(matrix_path))

    print(
        "PKG-015 launch gate verified: "
        f"items={len(REQUIRED_GAP_ITEMS)} runtime_gated_features={len(REQUIRED_RUNTIME_GATED_FEATURES)}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify PKG-015 B-launch readiness gate criteria."
    )
    parser.add_argument(
        "--gap-register",
        default="docs/ops/enforcement_control_plane_gap_register_2026-02-23.md",
        help="Gap register markdown path.",
    )
    parser.add_argument(
        "--matrix-path",
        default="docs/ops/feature_enforceability_matrix_2026-02-27.json",
        help="Feature enforceability matrix JSON path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    return verify_pkg015_launch_gate(
        gap_register_path=(repo_root / str(args.gap_register)).resolve(),
        matrix_path=(repo_root / str(args.matrix_path)).resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
