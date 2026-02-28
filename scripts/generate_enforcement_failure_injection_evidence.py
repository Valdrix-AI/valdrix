#!/usr/bin/env python3
"""Generate staged enforcement failure-injection evidence from real test execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class FailureScenario:
    scenario_id: str
    checks: tuple[str, ...]
    selectors: tuple[str, ...]


SCENARIOS: tuple[FailureScenario, ...] = (
    FailureScenario(
        scenario_id="FI-001",
        checks=("gate timeout failure routes to configured fail-safe behavior",),
        selectors=(
            "tests/unit/enforcement/test_enforcement_api.py::test_gate_failsafe_timeout_and_error_modes",
            "tests/unit/enforcement/test_enforcement_service.py::test_resolve_fail_safe_gate_timeout_mode_behavior",
        ),
    ),
    FailureScenario(
        scenario_id="FI-002",
        checks=("gate lock contention and timeout map to explicit fail-safe reason codes",),
        selectors=(
            "tests/unit/enforcement/test_enforcement_api.py::test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes",
            "tests/unit/enforcement/test_enforcement_service_helpers.py::test_acquire_gate_evaluation_lock_rowcount_zero_raises_contended_reason",
        ),
    ),
    FailureScenario(
        scenario_id="FI-003",
        checks=("approval token replay/tamper attempts are rejected under fault paths",),
        selectors=(
            "tests/unit/enforcement/test_enforcement_api.py::test_consume_approval_token_endpoint_rejects_replay_and_tamper",
            "tests/unit/enforcement/test_enforcement_service.py::test_consume_approval_token_rejects_replay",
        ),
    ),
    FailureScenario(
        scenario_id="FI-004",
        checks=("reservation reconciliation races remain idempotent and bounded",),
        selectors=(
            "tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_same_idempotency_key_settles_credit_once",
            "tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_overdue_claims_each_reservation_once",
        ),
    ),
    FailureScenario(
        scenario_id="FI-005",
        checks=("cross-tenant limiter saturation preserves global throttle behavior",),
        selectors=(
            "tests/unit/core/test_rate_limit.py::test_global_rate_limit_throttles_cross_tenant_requests",
            "tests/unit/enforcement/test_enforcement_api.py::test_enforcement_global_gate_limit_uses_configured_cap",
        ),
    ),
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute failure-injection scenarios and emit staged evidence JSON."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for generated evidence JSON artifact.",
    )
    parser.add_argument(
        "--executed-by",
        required=True,
        help="Execution owner identity (email/alias).",
    )
    parser.add_argument(
        "--approved-by",
        required=True,
        help="Approver identity (must be distinct from --executed-by).",
    )
    parser.add_argument(
        "--profile",
        default="enforcement_failure_injection",
        help="Evidence profile name.",
    )
    return parser.parse_args(argv)


def _run_scenario(scenario: FailureScenario, *, cwd: Path) -> tuple[dict[str, object], bool]:
    command = ["uv", "run", "pytest", "--no-cov", "-q", *scenario.selectors]
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = round(time.perf_counter() - started, 3)
    passed = result.returncode == 0
    scenario_payload = {
        "id": scenario.scenario_id,
        "status": "pass" if passed else "fail",
        "duration_seconds": max(duration_seconds, 0.001),
        "checks": list(scenario.checks),
        "evidence_refs": list(scenario.selectors),
        "command": " ".join(command),
        "result_tail": "\n".join(
            (result.stdout or "").strip().splitlines()[-10:]
            + (result.stderr or "").strip().splitlines()[-10:]
        ).strip(),
    }
    return scenario_payload, passed


def generate_evidence(
    *,
    output: Path,
    executed_by: str,
    approved_by: str,
    profile: str,
    cwd: Path,
) -> tuple[dict[str, object], bool]:
    if executed_by.strip() == approved_by.strip():
        raise ValueError("executed_by and approved_by must be distinct")

    scenario_rows: list[dict[str, object]] = []
    passed_count = 0
    for scenario in SCENARIOS:
        payload, passed = _run_scenario(scenario, cwd=cwd)
        scenario_rows.append(payload)
        if passed:
            passed_count += 1

    total = len(scenario_rows)
    failed = total - passed_count
    overall_passed = failed == 0

    artifact: dict[str, object] = {
        "profile": profile,
        "runner": "staged_failure_injection",
        "execution_class": "staged",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "executed_by": executed_by.strip(),
        "approved_by": approved_by.strip(),
        "scenarios": scenario_rows,
        "summary": {
            "total_scenarios": total,
            "passed_scenarios": passed_count,
            "failed_scenarios": failed,
            "overall_passed": overall_passed,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact, overall_passed


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact, passed = generate_evidence(
        output=Path(args.output),
        executed_by=str(args.executed_by),
        approved_by=str(args.approved_by),
        profile=str(args.profile),
        cwd=Path(__file__).resolve().parents[1],
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
