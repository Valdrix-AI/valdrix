"""Validate enforcement stress evidence produced by scripts/load_test_api.py."""

from __future__ import annotations

import argparse
import json
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


def verify_evidence(
    *,
    evidence_path: Path,
    expected_profile: str,
    min_rounds: int,
    max_p95_seconds: float,
    max_error_rate_percent: float,
    min_throughput_rps: float,
) -> int:
    payload = _load_payload(evidence_path)

    profile = str(payload.get("profile") or "").strip().lower()
    if profile != expected_profile.lower():
        raise ValueError(
            f"Unexpected profile {profile!r}; expected {expected_profile!r}"
        )

    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("endpoints must be a non-empty array")
    normalized_endpoints = [str(item) for item in endpoints]
    if not any(item.startswith("/api/v1/enforcement/") for item in normalized_endpoints):
        raise ValueError("evidence must include enforcement API endpoints")

    rounds = _parse_int(payload.get("rounds"), field="rounds")
    if rounds < min_rounds:
        raise ValueError(f"rounds must be >= {min_rounds}, got {rounds}")

    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("preflight must be an object")
    if bool(preflight.get("enabled")) is not True:
        raise ValueError("preflight.enabled must be true for stress evidence")
    if bool(preflight.get("passed")) is not True:
        raise ValueError("preflight.passed must be true for stress evidence")

    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("results must be an object")
    total_requests = _parse_int(results.get("total_requests"), field="results.total_requests")
    failed_requests = _parse_int(results.get("failed_requests"), field="results.failed_requests")
    if total_requests <= 0:
        raise ValueError("results.total_requests must be > 0")
    if failed_requests < 0 or failed_requests > total_requests:
        raise ValueError("results.failed_requests must be between 0 and total_requests")

    p95_seconds = _parse_float(results.get("p95_response_time"), field="results.p95_response_time")
    if p95_seconds > max_p95_seconds:
        raise ValueError(
            f"p95_response_time {p95_seconds:.4f}s exceeds max {max_p95_seconds:.4f}s"
        )

    throughput = _parse_float(payload.get("min_throughput_rps"), field="min_throughput_rps")
    if throughput < min_throughput_rps:
        raise ValueError(
            f"min_throughput_rps {throughput:.4f} is below required {min_throughput_rps:.4f}"
        )

    error_rate_percent = (failed_requests / total_requests) * 100.0
    if error_rate_percent > max_error_rate_percent:
        raise ValueError(
            "error rate "
            f"{error_rate_percent:.4f}% exceeds max {max_error_rate_percent:.4f}%"
        )

    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("evaluation must be present for stress evidence")
    if bool(evaluation.get("overall_meets_targets")) is not True:
        raise ValueError("evaluation.overall_meets_targets must be true")

    print(
        "Enforcement stress evidence verified: "
        f"profile={profile} rounds={rounds} total_requests={total_requests} "
        f"p95={p95_seconds:.4f}s error_rate={error_rate_percent:.4f}% "
        f"min_throughput_rps={throughput:.4f}"
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_evidence(
        evidence_path=Path(str(args.evidence_path)),
        expected_profile=str(args.expected_profile),
        min_rounds=int(args.min_rounds),
        max_p95_seconds=float(args.max_p95_seconds),
        max_error_rate_percent=float(args.max_error_rate_percent),
        min_throughput_rps=float(args.min_throughput_rps),
    )


if __name__ == "__main__":
    raise SystemExit(main())
