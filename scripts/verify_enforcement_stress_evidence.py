"""Validate enforcement stress evidence produced by scripts/load_test_api.py."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _rounded_eq(lhs: float, rhs: float, *, places: int = 4) -> bool:
    return round(float(lhs), places) == round(float(rhs), places)


def _canonical_database_engine(value: Any, *, field: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError(f"{field} must be a non-empty string")
    base = raw.split("://", 1)[0].split("+", 1)[0]
    if base.startswith("postgres"):
        return "postgresql"
    if base.startswith("sqlite"):
        return "sqlite"
    return base


def verify_evidence(
    *,
    evidence_path: Path,
    expected_profile: str,
    min_rounds: int,
    min_duration_seconds: int,
    min_concurrent_users: int,
    required_database_engine: str,
    max_p95_seconds: float,
    max_error_rate_percent: float,
    min_throughput_rps: float,
    max_artifact_age_hours: float | None = None,
) -> int:
    payload = _load_payload(evidence_path)

    profile = str(payload.get("profile") or "").strip().lower()
    if profile != expected_profile.lower():
        raise ValueError(
            f"Unexpected profile {profile!r}; expected {expected_profile!r}"
        )

    runner = str(payload.get("runner") or "").strip()
    if runner != "scripts/load_test_api.py":
        raise ValueError("runner must equal 'scripts/load_test_api.py'")

    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    actual_database_engine = _canonical_database_engine(
        runtime.get("database_engine"),
        field="runtime.database_engine",
    )
    expected_database_engine = _canonical_database_engine(
        required_database_engine,
        field="required_database_engine",
    )
    if actual_database_engine != expected_database_engine:
        raise ValueError(
            "runtime.database_engine does not match required verifier backend "
            f"({actual_database_engine!r} != {expected_database_engine!r})"
        )

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

    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("endpoints must be a non-empty array")
    normalized_endpoints = [str(item) for item in endpoints]
    if not any(item.startswith("/api/v1/enforcement/") for item in normalized_endpoints):
        raise ValueError("evidence must include enforcement API endpoints")
    required_endpoints = {
        "/api/v1/enforcement/policies",
        "/api/v1/enforcement/ledger?limit=50",
        "/api/v1/enforcement/exports/parity?limit=50",
    }
    missing_required_endpoints = required_endpoints.difference(normalized_endpoints)
    if missing_required_endpoints:
        missing_sorted = ", ".join(sorted(missing_required_endpoints))
        raise ValueError(
            "evidence is missing required enforcement endpoints: "
            f"{missing_sorted}"
        )

    rounds = _parse_int(payload.get("rounds"), field="rounds")
    if rounds < min_rounds:
        raise ValueError(f"rounds must be >= {min_rounds}, got {rounds}")

    duration_seconds = _parse_int(
        payload.get("duration_seconds"),
        field="duration_seconds",
    )
    if duration_seconds < min_duration_seconds:
        raise ValueError(
            "duration_seconds must be >= "
            f"{min_duration_seconds}, got {duration_seconds}"
        )
    concurrent_users = _parse_int(
        payload.get("concurrent_users"),
        field="concurrent_users",
    )
    if concurrent_users < min_concurrent_users:
        raise ValueError(
            "concurrent_users must be >= "
            f"{min_concurrent_users}, got {concurrent_users}"
        )

    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) < rounds:
        raise ValueError("runs must be an array with at least `rounds` entries")
    runs_considered = runs[:rounds]

    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("preflight must be an object")
    if bool(preflight.get("enabled")) is not True:
        raise ValueError("preflight.enabled must be true for stress evidence")
    if bool(preflight.get("passed")) is not True:
        raise ValueError("preflight.passed must be true for stress evidence")
    preflight_failures = preflight.get("failures")
    if isinstance(preflight_failures, list) and preflight_failures:
        raise ValueError("preflight.failures must be empty when preflight.passed is true")

    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("results must be an object")
    total_requests = _parse_int(results.get("total_requests"), field="results.total_requests")
    failed_requests = _parse_int(results.get("failed_requests"), field="results.failed_requests")
    if total_requests <= 0:
        raise ValueError("results.total_requests must be > 0")
    if failed_requests < 0 or failed_requests > total_requests:
        raise ValueError("results.failed_requests must be between 0 and total_requests")
    successful_requests = _parse_int(
        results.get("successful_requests"),
        field="results.successful_requests",
    )
    if successful_requests != (total_requests - failed_requests):
        raise ValueError(
            "results.successful_requests must equal total_requests - failed_requests"
        )

    p95_seconds = _parse_float(results.get("p95_response_time"), field="results.p95_response_time")
    if p95_seconds > max_p95_seconds:
        raise ValueError(
            f"p95_response_time {p95_seconds:.4f}s exceeds max {max_p95_seconds:.4f}s"
        )
    throughput_rps = _parse_float(
        results.get("throughput_rps"),
        field="results.throughput_rps",
    )
    if throughput_rps <= 0:
        raise ValueError("results.throughput_rps must be > 0")

    throughput = _parse_float(payload.get("min_throughput_rps"), field="min_throughput_rps")
    if throughput < min_throughput_rps:
        raise ValueError(
            f"min_throughput_rps {throughput:.4f} is below required {min_throughput_rps:.4f}"
        )

    run_total_requests = 0
    run_successful_requests = 0
    run_failed_requests = 0
    run_p95_values: list[float] = []
    run_p99_values: list[float] = []
    run_throughput_values: list[float] = []
    for idx, run in enumerate(runs_considered, start=1):
        if not isinstance(run, dict):
            raise ValueError(f"runs[{idx - 1}] must be an object")
        run_index = _parse_int(run.get("run_index"), field=f"runs[{idx - 1}].run_index")
        if run_index != idx:
            raise ValueError(
                f"runs[{idx - 1}].run_index must equal {idx}, got {run_index}"
            )
        _parse_iso_utc(run.get("captured_at"), field=f"runs[{idx - 1}].captured_at")
        run_results = run.get("results")
        if not isinstance(run_results, dict):
            raise ValueError(f"runs[{idx - 1}].results must be an object")

        run_total = _parse_int(
            run_results.get("total_requests"),
            field=f"runs[{idx - 1}].results.total_requests",
        )
        run_success = _parse_int(
            run_results.get("successful_requests"),
            field=f"runs[{idx - 1}].results.successful_requests",
        )
        run_failed = _parse_int(
            run_results.get("failed_requests"),
            field=f"runs[{idx - 1}].results.failed_requests",
        )
        if run_success != (run_total - run_failed):
            raise ValueError(
                "runs[%d].results.successful_requests must equal total_requests - failed_requests"
                % (idx - 1)
            )
        run_total_requests += run_total
        run_successful_requests += run_success
        run_failed_requests += run_failed
        run_p95_values.append(
            _parse_float(
                run_results.get("p95_response_time"),
                field=f"runs[{idx - 1}].results.p95_response_time",
            )
        )
        run_p99_values.append(
            _parse_float(
                run_results.get("p99_response_time"),
                field=f"runs[{idx - 1}].results.p99_response_time",
            )
        )
        run_throughput_values.append(
            _parse_float(
                run_results.get("throughput_rps"),
                field=f"runs[{idx - 1}].results.throughput_rps",
            )
        )

    if run_total_requests != total_requests:
        raise ValueError("results.total_requests must equal sum(runs[*].results.total_requests)")
    if run_successful_requests != successful_requests:
        raise ValueError(
            "results.successful_requests must equal sum(runs[*].results.successful_requests)"
        )
    if run_failed_requests != failed_requests:
        raise ValueError("results.failed_requests must equal sum(runs[*].results.failed_requests)")
    if not _rounded_eq(max(run_p95_values), p95_seconds):
        raise ValueError("results.p95_response_time must equal max(runs[*].results.p95_response_time)")
    if not _rounded_eq(max(run_p99_values), _parse_float(results.get("p99_response_time"), field="results.p99_response_time")):
        raise ValueError("results.p99_response_time must equal max(runs[*].results.p99_response_time)")
    if not _rounded_eq(min(run_throughput_values), throughput):
        raise ValueError("min_throughput_rps must equal min(runs[*].results.throughput_rps)")
    avg_run_throughput = sum(run_throughput_values) / max(1, len(run_throughput_values))
    if not _rounded_eq(avg_run_throughput, throughput_rps):
        raise ValueError("results.throughput_rps must equal avg(runs[*].results.throughput_rps)")

    error_rate_percent = (failed_requests / total_requests) * 100.0
    if error_rate_percent > max_error_rate_percent:
        raise ValueError(
            "error rate "
            f"{error_rate_percent:.4f}% exceeds max {max_error_rate_percent:.4f}%"
        )

    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be present for stress evidence")
    threshold_max_p95 = _parse_float(
        thresholds.get("max_p95_seconds"),
        field="thresholds.max_p95_seconds",
    )
    threshold_max_error = _parse_float(
        thresholds.get("max_error_rate_percent"),
        field="thresholds.max_error_rate_percent",
    )
    threshold_min_throughput = _parse_float(
        thresholds.get("min_throughput_rps"),
        field="thresholds.min_throughput_rps",
    )
    if not _rounded_eq(threshold_max_p95, float(max_p95_seconds)):
        raise ValueError("thresholds.max_p95_seconds must match verifier max_p95_seconds")
    if not _rounded_eq(threshold_max_error, float(max_error_rate_percent)):
        raise ValueError(
            "thresholds.max_error_rate_percent must match verifier max_error_rate_percent"
        )
    if not _rounded_eq(threshold_min_throughput, float(min_throughput_rps)):
        raise ValueError(
            "thresholds.min_throughput_rps must match verifier min_throughput_rps"
        )

    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("evaluation must be present for stress evidence")
    evaluation_worst_p95 = _parse_float(
        evaluation.get("worst_p95_seconds"),
        field="evaluation.worst_p95_seconds",
    )
    evaluation_min_throughput = _parse_float(
        evaluation.get("min_throughput_rps"),
        field="evaluation.min_throughput_rps",
    )
    if not _rounded_eq(evaluation_worst_p95, p95_seconds):
        raise ValueError("evaluation.worst_p95_seconds must equal results.p95_response_time")
    if not _rounded_eq(evaluation_min_throughput, throughput):
        raise ValueError("evaluation.min_throughput_rps must equal min_throughput_rps")
    evaluation_rounds = evaluation.get("rounds")
    if not isinstance(evaluation_rounds, list) or len(evaluation_rounds) != rounds:
        raise ValueError("evaluation.rounds must include exactly `rounds` entries")
    computed_overall = all(bool(item.get("meets_targets")) for item in evaluation_rounds)
    declared_overall = bool(evaluation.get("overall_meets_targets"))
    if declared_overall is not computed_overall:
        raise ValueError(
            "evaluation.overall_meets_targets must match all(evaluation.rounds[*].meets_targets)"
        )
    if bool(evaluation.get("overall_meets_targets")) is not True:
        raise ValueError("evaluation.overall_meets_targets must be true")
    if "meets_targets" in payload and bool(payload.get("meets_targets")) is not True:
        raise ValueError("meets_targets must be true when evaluation.overall_meets_targets is true")

    print(
        "Enforcement stress evidence verified: "
        f"profile={profile} rounds={rounds} total_requests={total_requests} "
        f"p95={p95_seconds:.4f}s error_rate={error_rate_percent:.4f}% "
        f"min_throughput_rps={throughput:.4f} throughput_rps={throughput_rps:.4f} "
        f"database_engine={actual_database_engine}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate enforcement stress evidence JSON payload."
    )
    parser.add_argument(
        "--evidence-path",
        required=True,
        help="Path to JSON evidence produced by scripts/load_test_api.py",
    )
    parser.add_argument(
        "--expected-profile",
        default="enforcement",
        help="Expected load-test profile name (default: enforcement).",
    )
    parser.add_argument(
        "--min-rounds",
        type=int,
        default=3,
        help="Minimum required rounds in the evidence payload.",
    )
    parser.add_argument(
        "--min-duration-seconds",
        type=int,
        default=30,
        help="Minimum allowed test duration in seconds.",
    )
    parser.add_argument(
        "--min-concurrent-users",
        type=int,
        default=10,
        help="Minimum allowed concurrent users for release evidence.",
    )
    parser.add_argument(
        "--required-database-engine",
        default="postgresql",
        help="Required DB backend engine captured in evidence runtime metadata.",
    )
    parser.add_argument(
        "--max-p95-seconds",
        type=float,
        default=2.0,
        help="Maximum allowed p95 response time in seconds.",
    )
    parser.add_argument(
        "--max-error-rate-percent",
        type=float,
        default=1.0,
        help="Maximum allowed failed-request ratio (percent).",
    )
    parser.add_argument(
        "--min-throughput-rps",
        type=float,
        default=0.5,
        help="Minimum required throughput in requests/sec.",
    )
    parser.add_argument(
        "--max-artifact-age-hours",
        type=float,
        default=None,
        help=(
            "Optional freshness bound; fail when captured_at is older than this "
            "many hours."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_evidence(
        evidence_path=Path(str(args.evidence_path)),
        expected_profile=str(args.expected_profile),
        min_rounds=int(args.min_rounds),
        min_duration_seconds=int(args.min_duration_seconds),
        min_concurrent_users=int(args.min_concurrent_users),
        required_database_engine=str(args.required_database_engine),
        max_p95_seconds=float(args.max_p95_seconds),
        max_error_rate_percent=float(args.max_error_rate_percent),
        min_throughput_rps=float(args.min_throughput_rps),
        max_artifact_age_hours=(
            float(args.max_artifact_age_hours)
            if args.max_artifact_age_hours is not None
            else None
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
