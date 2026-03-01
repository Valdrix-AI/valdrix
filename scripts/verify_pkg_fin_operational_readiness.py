#!/usr/bin/env python3
"""Summarize PKG/FIN operational readiness from existing evidence contracts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.verify_finance_guardrails_evidence import (
    verify_evidence as verify_finance_guardrails_evidence,
)
from scripts.verify_finance_telemetry_snapshot import (
    verify_snapshot as verify_finance_telemetry_snapshot,
)
from scripts.verify_pkg_fin_policy_decisions import (
    verify_evidence as verify_pkg_fin_policy_decisions_evidence,
)


def _load_json_object(path: Path, *, field: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{field} file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} payload must be a JSON object")
    return payload


def _read_bool_gate_map(payload: dict[str, Any], *, prefix: str) -> dict[str, bool]:
    gates = payload.get("gate_results")
    if not isinstance(gates, dict):
        raise ValueError("gate_results must be an object")
    selected = {k: v for k, v in gates.items() if k.startswith(prefix)}
    if not selected:
        raise ValueError(f"gate_results missing entries for prefix: {prefix}")

    normalized: dict[str, bool] = {}
    for key, value in selected.items():
        if not isinstance(value, bool):
            raise ValueError(f"gate_results.{key} must be boolean")
        normalized[key] = value
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def verify_operational_readiness(
    *,
    policy_decisions_path: Path,
    finance_guardrails_path: Path,
    telemetry_snapshot_path: Path,
    max_policy_age_hours: float | None = None,
    max_finance_age_hours: float | None = None,
    max_telemetry_age_hours: float | None = None,
    allow_failed_fin_gates: bool = False,
    require_production_observed_telemetry: bool = False,
    require_segregated_owners: bool = False,
) -> dict[str, Any]:
    verify_pkg_fin_policy_decisions_evidence(
        evidence_path=policy_decisions_path,
        max_artifact_age_hours=max_policy_age_hours,
    )
    verify_finance_guardrails_evidence(
        evidence_path=finance_guardrails_path,
        max_artifact_age_hours=max_finance_age_hours,
        allow_failed_gates=allow_failed_fin_gates,
    )
    verify_finance_telemetry_snapshot(
        snapshot_path=telemetry_snapshot_path,
        max_artifact_age_hours=max_telemetry_age_hours,
    )

    policy_payload = _load_json_object(policy_decisions_path, field="policy_decisions")
    finance_payload = _load_json_object(finance_guardrails_path, field="finance_guardrails")
    telemetry_payload = _load_json_object(telemetry_snapshot_path, field="telemetry_snapshot")

    policy_gates = _read_bool_gate_map(policy_payload, prefix="pkg_fin_gate_")
    finance_gates = _read_bool_gate_map(finance_payload, prefix="fin_gate_")
    telemetry_gates = _read_bool_gate_map(telemetry_payload, prefix="telemetry_gate_")

    telemetry = policy_payload.get("telemetry")
    if not isinstance(telemetry, dict):
        raise ValueError("policy_decisions.telemetry must be an object")
    months_observed_raw = telemetry.get("months_observed")
    try:
        months_observed = int(months_observed_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("policy_decisions.telemetry.months_observed must be integer-like") from exc
    telemetry_source_type = str(telemetry.get("source_type") or "").strip().lower()
    if not telemetry_source_type:
        raise ValueError("policy_decisions.telemetry.source_type must be non-empty")

    approvals = policy_payload.get("approvals")
    if not isinstance(approvals, dict):
        raise ValueError("policy_decisions.approvals must be an object")
    governance_mode = str(approvals.get("governance_mode") or "").strip().lower()
    if not governance_mode:
        raise ValueError("policy_decisions.approvals.governance_mode must be non-empty")

    production_observed_telemetry_ready = (
        telemetry_source_type == "production_observed" and months_observed >= 2
    )
    segregated_approval_governance_ready = governance_mode == "segregated_owners"

    policy_all_gates_pass = all(policy_gates.values())
    finance_all_gates_pass = all(finance_gates.values())
    telemetry_all_gates_pass = all(telemetry_gates.values())

    prelaunch_operational_ready = (
        policy_all_gates_pass and finance_all_gates_pass and telemetry_all_gates_pass
    )
    postlaunch_pricing_motion_ready = (
        prelaunch_operational_ready
        and production_observed_telemetry_ready
        and segregated_approval_governance_ready
    )

    remaining_work_items: list[str] = []
    if not production_observed_telemetry_ready:
        remaining_work_items.append(
            "Collect >=2 months production_observed telemetry and refresh PKG/FIN policy evidence."
        )
    if not segregated_approval_governance_ready:
        remaining_work_items.append(
            "Move approvals.governance_mode to segregated_owners with distinct finance/product/go-to-market owners."
        )

    if require_production_observed_telemetry and not production_observed_telemetry_ready:
        raise ValueError(
            "production_observed telemetry requirement failed: "
            f"source_type={telemetry_source_type}, months_observed={months_observed}"
        )
    if require_segregated_owners and not segregated_approval_governance_ready:
        raise ValueError(
            "segregated owner governance requirement failed: "
            f"governance_mode={governance_mode}"
        )

    summary: dict[str, Any] = {
        "generated_at": _utc_now_iso(),
        "artifacts": {
            "policy_decisions_path": str(policy_decisions_path),
            "finance_guardrails_path": str(finance_guardrails_path),
            "telemetry_snapshot_path": str(telemetry_snapshot_path),
        },
        "gates": {
            "policy": policy_gates,
            "finance": finance_gates,
            "telemetry": telemetry_gates,
        },
        "derived": {
            "policy_all_gates_pass": policy_all_gates_pass,
            "finance_all_gates_pass": finance_all_gates_pass,
            "telemetry_all_gates_pass": telemetry_all_gates_pass,
            "prelaunch_operational_ready": prelaunch_operational_ready,
            "postlaunch_pricing_motion_ready": postlaunch_pricing_motion_ready,
            "production_observed_telemetry_ready": production_observed_telemetry_ready,
            "segregated_approval_governance_ready": segregated_approval_governance_ready,
            "telemetry_source_type": telemetry_source_type,
            "months_observed": months_observed,
            "approval_governance_mode": governance_mode,
        },
        "remaining_work_items": remaining_work_items,
    }
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify PKG/FIN operational readiness by composing policy, finance, "
            "and telemetry evidence checks."
        )
    )
    parser.add_argument(
        "--policy-decisions-path",
        required=True,
        help="Path to pkg_fin_policy_decisions evidence JSON.",
    )
    parser.add_argument(
        "--finance-guardrails-path",
        required=True,
        help="Path to finance_guardrails evidence JSON.",
    )
    parser.add_argument(
        "--telemetry-snapshot-path",
        required=True,
        help="Path to finance_telemetry_snapshot evidence JSON.",
    )
    parser.add_argument(
        "--max-policy-age-hours",
        type=float,
        default=None,
        help="Optional max age for policy decision artifact in hours.",
    )
    parser.add_argument(
        "--max-finance-age-hours",
        type=float,
        default=None,
        help="Optional max age for finance guardrails artifact in hours.",
    )
    parser.add_argument(
        "--max-telemetry-age-hours",
        type=float,
        default=None,
        help="Optional max age for telemetry snapshot artifact in hours.",
    )
    parser.add_argument(
        "--allow-failed-fin-gates",
        action="store_true",
        help="Allow failed FIN gates while still validating artifact integrity.",
    )
    parser.add_argument(
        "--require-production-observed-telemetry",
        action="store_true",
        help="Fail unless source_type=production_observed and months_observed>=2.",
    )
    parser.add_argument(
        "--require-segregated-owners",
        action="store_true",
        help="Fail unless approvals.governance_mode=segregated_owners.",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional JSON output path for readiness summary.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = verify_operational_readiness(
        policy_decisions_path=Path(str(args.policy_decisions_path)),
        finance_guardrails_path=Path(str(args.finance_guardrails_path)),
        telemetry_snapshot_path=Path(str(args.telemetry_snapshot_path)),
        max_policy_age_hours=(
            float(args.max_policy_age_hours) if args.max_policy_age_hours is not None else None
        ),
        max_finance_age_hours=(
            float(args.max_finance_age_hours)
            if args.max_finance_age_hours is not None
            else None
        ),
        max_telemetry_age_hours=(
            float(args.max_telemetry_age_hours)
            if args.max_telemetry_age_hours is not None
            else None
        ),
        allow_failed_fin_gates=bool(args.allow_failed_fin_gates),
        require_production_observed_telemetry=bool(
            args.require_production_observed_telemetry
        ),
        require_segregated_owners=bool(args.require_segregated_owners),
    )
    if args.output_path:
        output_path = Path(str(args.output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
