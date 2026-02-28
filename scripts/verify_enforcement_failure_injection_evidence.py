"""Validate staged enforcement failure-injection evidence artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_SCENARIO_IDS: tuple[str, ...] = (
    "FI-001",
    "FI-002",
    "FI-003",
    "FI-004",
    "FI-005",
)


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Evidence file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Evidence JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Evidence payload must be a JSON object")
    return payload


def _parse_iso_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty ISO-8601 datetime")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _parse_float(value: Any, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _parse_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be integer-like") from exc


def verify_evidence(
    *,
    evidence_path: Path,
    expected_profile: str,
    max_artifact_age_hours: float | None = None,
) -> int:
    payload = _load_payload(evidence_path)

    profile = str(payload.get("profile") or "").strip().lower()
    if profile != expected_profile.strip().lower():
        raise ValueError(
            f"Unexpected profile {profile!r}; expected {expected_profile!r}"
        )

    runner = str(payload.get("runner") or "").strip()
    if runner != "staged_failure_injection":
        raise ValueError("runner must equal 'staged_failure_injection'")

    execution_class = str(payload.get("execution_class") or "").strip().lower()
    if execution_class != "staged":
        raise ValueError("execution_class must be 'staged'")

    captured_at_utc = _parse_iso_utc(payload.get("captured_at"), field="captured_at")
    if max_artifact_age_hours is not None:
        max_age = float(max_artifact_age_hours)
        if max_age <= 0:
            raise ValueError("max_artifact_age_hours must be > 0 when provided")
        age_hours = (
            datetime.now(timezone.utc) - captured_at_utc
        ).total_seconds() / 3600.0
        if age_hours > max_age:
            raise ValueError(
                "captured_at is too old for release verification "
                f"({age_hours:.2f}h > max {max_age:.2f}h)"
            )

    executed_by = str(payload.get("executed_by") or "").strip()
    approved_by = str(payload.get("approved_by") or "").strip()
    if not executed_by or not approved_by:
        raise ValueError("executed_by and approved_by must be non-empty")
    if executed_by == approved_by:
        raise ValueError("executed_by and approved_by must be distinct")

    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a non-empty array")

    seen_ids: set[str] = set()
    passed_count = 0
    for idx, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(f"scenarios[{idx}] must be an object")
        scenario_id = str(scenario.get("id") or "").strip().upper()
        if not scenario_id:
            raise ValueError(f"scenarios[{idx}].id must be non-empty")
        if scenario_id in seen_ids:
            raise ValueError(f"Duplicate scenario id in evidence: {scenario_id}")
        seen_ids.add(scenario_id)
        if scenario_id not in REQUIRED_SCENARIO_IDS:
            raise ValueError(f"Unknown scenario id in evidence: {scenario_id}")

        status = str(scenario.get("status") or "").strip().lower()
        if status not in {"pass", "fail"}:
            raise ValueError(f"scenarios[{idx}].status must be pass|fail")
        if status == "pass":
            passed_count += 1

        duration_seconds = _parse_float(
            scenario.get("duration_seconds"),
            field=f"scenarios[{idx}].duration_seconds",
        )
        if duration_seconds <= 0:
            raise ValueError(f"scenarios[{idx}].duration_seconds must be > 0")

        checks = scenario.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"scenarios[{idx}].checks must be a non-empty array")
        if not all(bool(str(item).strip()) for item in checks):
            raise ValueError(f"scenarios[{idx}].checks must contain non-empty entries")

        evidence_refs = scenario.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ValueError(
                f"scenarios[{idx}].evidence_refs must be a non-empty array"
            )
        if not all(bool(str(item).strip()) for item in evidence_refs):
            raise ValueError(
                f"scenarios[{idx}].evidence_refs must contain non-empty entries"
            )

    missing_ids = sorted(set(REQUIRED_SCENARIO_IDS) - seen_ids)
    if missing_ids:
        raise ValueError(
            "Evidence is missing required failure scenarios: " + ", ".join(missing_ids)
        )

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")

    declared_total = _parse_int(
        summary.get("total_scenarios"),
        field="summary.total_scenarios",
    )
    declared_passed = _parse_int(
        summary.get("passed_scenarios"),
        field="summary.passed_scenarios",
    )
    declared_failed = _parse_int(
        summary.get("failed_scenarios"),
        field="summary.failed_scenarios",
    )
    declared_overall = bool(summary.get("overall_passed"))

    if declared_total != len(scenarios):
        raise ValueError("summary.total_scenarios must equal len(scenarios)")
    if declared_passed != passed_count:
        raise ValueError("summary.passed_scenarios must equal count(status=pass)")
    if declared_failed != (declared_total - declared_passed):
        raise ValueError(
            "summary.failed_scenarios must equal total_scenarios - passed_scenarios"
        )
    if declared_overall is not (declared_failed == 0):
        raise ValueError("summary.overall_passed must match failed_scenarios == 0")
    if not declared_overall:
        raise ValueError("summary.overall_passed must be true for release evidence")

    print(
        "Enforcement failure-injection evidence verified "
        f"(scenarios={declared_total}, captured_at={captured_at_utc.isoformat()})"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate staged enforcement failure-injection evidence artifact."
    )
    parser.add_argument(
        "--evidence-path",
        required=True,
        help="Path to staged failure-injection evidence JSON.",
    )
    parser.add_argument(
        "--expected-profile",
        default="enforcement_failure_injection",
        help="Expected profile name inside evidence payload.",
    )
    parser.add_argument(
        "--max-artifact-age-hours",
        type=float,
        default=None,
        help="Optional freshness bound for captured_at timestamp.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_evidence(
        evidence_path=Path(str(args.evidence_path)),
        expected_profile=str(args.expected_profile),
        max_artifact_age_hours=args.max_artifact_age_hours,
    )


if __name__ == "__main__":
    raise SystemExit(main())
