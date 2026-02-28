"""Run enterprise gate with staged enforcement evidence requirements enabled."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from pathlib import Path


def _assert_file(path: Path, *, field: str) -> Path:
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"{field} does not exist or is not a file: {path}")
    return resolved


def _assert_positive_int(value: int, *, field: str) -> int:
    if int(value) <= 0:
        raise ValueError(f"{field} must be > 0")
    return int(value)


def _assert_positive_float(value: float, *, field: str) -> float:
    if float(value) <= 0:
        raise ValueError(f"{field} must be > 0")
    return float(value)


def _assert_non_empty_str(value: str, *, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def build_gate_environment(
    *,
    stress_evidence_path: Path,
    failure_evidence_path: Path,
    finance_evidence_path: Path | None,
    finance_evidence_required: bool,
    pricing_benchmark_register_path: Path | None,
    pricing_benchmark_register_required: bool,
    stress_max_age_hours: float,
    failure_max_age_hours: float,
    finance_max_age_hours: float,
    pricing_benchmark_max_source_age_days: float,
    stress_min_duration_seconds: int,
    stress_min_concurrent_users: int,
    stress_required_database_engine: str,
) -> dict[str, str]:
    stress_path = _assert_file(stress_evidence_path, field="stress_evidence_path")
    failure_path = _assert_file(failure_evidence_path, field="failure_evidence_path")
    finance_path: Path | None = None
    if finance_evidence_path is not None:
        finance_path = _assert_file(finance_evidence_path, field="finance_evidence_path")
    if finance_evidence_required and finance_path is None:
        raise ValueError(
            "finance_evidence_required is true but finance_evidence_path is not provided"
        )
    pricing_benchmark_path: Path | None = None
    if pricing_benchmark_register_path is not None:
        pricing_benchmark_path = _assert_file(
            pricing_benchmark_register_path,
            field="pricing_benchmark_register_path",
        )
    if pricing_benchmark_register_required and pricing_benchmark_path is None:
        raise ValueError(
            "pricing_benchmark_register_required is true but "
            "pricing_benchmark_register_path is not provided"
        )
    validated_stress_max_age = _assert_positive_float(
        stress_max_age_hours,
        field="stress_max_age_hours",
    )
    validated_failure_max_age = _assert_positive_float(
        failure_max_age_hours,
        field="failure_max_age_hours",
    )
    validated_finance_max_age = _assert_positive_float(
        finance_max_age_hours,
        field="finance_max_age_hours",
    )
    validated_pricing_benchmark_max_age_days = _assert_positive_float(
        pricing_benchmark_max_source_age_days,
        field="pricing_benchmark_max_source_age_days",
    )
    validated_duration = _assert_positive_int(
        stress_min_duration_seconds,
        field="stress_min_duration_seconds",
    )
    validated_users = _assert_positive_int(
        stress_min_concurrent_users,
        field="stress_min_concurrent_users",
    )
    validated_required_database_engine = _assert_non_empty_str(
        stress_required_database_engine,
        field="stress_required_database_engine",
    )

    env = os.environ.copy()
    env["ENFORCEMENT_STRESS_EVIDENCE_PATH"] = str(stress_path)
    env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED"] = "true"
    env["ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS"] = str(validated_stress_max_age)
    env["ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS"] = str(validated_duration)
    env["ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS"] = str(validated_users)
    env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE"] = (
        validated_required_database_engine
    )

    env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH"] = str(failure_path)
    env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED"] = "true"
    env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS"] = str(
        validated_failure_max_age
    )
    env.pop("ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH", None)
    env.pop("ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED", None)
    env.pop("ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS", None)
    env.pop("ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH", None)
    env.pop("ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED", None)
    env.pop("ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS", None)
    if finance_path is not None:
        env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH"] = str(finance_path)
        env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED"] = "true"
        env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS"] = str(
            validated_finance_max_age
        )
    if pricing_benchmark_path is not None:
        env["ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH"] = str(
            pricing_benchmark_path
        )
        env["ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED"] = "true"
        env["ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS"] = str(
            validated_pricing_benchmark_max_age_days
        )
    return env


def run_release_gate(
    *,
    stress_evidence_path: Path,
    failure_evidence_path: Path,
    finance_evidence_path: Path | None,
    finance_evidence_required: bool,
    pricing_benchmark_register_path: Path | None,
    pricing_benchmark_register_required: bool,
    stress_max_age_hours: float,
    failure_max_age_hours: float,
    finance_max_age_hours: float,
    pricing_benchmark_max_source_age_days: float,
    stress_min_duration_seconds: int,
    stress_min_concurrent_users: int,
    stress_required_database_engine: str,
    dry_run: bool,
) -> int:
    env = build_gate_environment(
        stress_evidence_path=stress_evidence_path,
        failure_evidence_path=failure_evidence_path,
        finance_evidence_path=finance_evidence_path,
        finance_evidence_required=finance_evidence_required,
        pricing_benchmark_register_path=pricing_benchmark_register_path,
        pricing_benchmark_register_required=pricing_benchmark_register_required,
        stress_max_age_hours=stress_max_age_hours,
        failure_max_age_hours=failure_max_age_hours,
        finance_max_age_hours=finance_max_age_hours,
        pricing_benchmark_max_source_age_days=pricing_benchmark_max_source_age_days,
        stress_min_duration_seconds=stress_min_duration_seconds,
        stress_min_concurrent_users=stress_min_concurrent_users,
        stress_required_database_engine=stress_required_database_engine,
    )

    cmd = ["uv", "run", "python3", "scripts/run_enterprise_tdd_gate.py"]
    if dry_run:
        cmd.append("--dry-run")
    print(f"[enforcement-release-gate] {' '.join(shlex.quote(part) for part in cmd)}")
    completed = subprocess.run(cmd, check=False, env=env)
    return int(completed.returncode)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run enterprise gate with both staged enforcement stress and "
            "failure-injection evidence requirements enforced."
        )
    )
    parser.add_argument(
        "--stress-evidence-path",
        required=True,
        help="Path to staged enforcement stress evidence JSON.",
    )
    parser.add_argument(
        "--failure-evidence-path",
        required=True,
        help="Path to staged enforcement failure-injection evidence JSON.",
    )
    parser.add_argument(
        "--finance-evidence-path",
        default=None,
        help=(
            "Optional path to staged finance guardrails evidence JSON. "
            "When provided, finance gate verification is enforced."
        ),
    )
    parser.add_argument(
        "--finance-evidence-required",
        action="store_true",
        help=(
            "Require finance guardrails evidence verification. "
            "When set, --finance-evidence-path must be provided."
        ),
    )
    parser.add_argument(
        "--pricing-benchmark-register-path",
        default=None,
        help=(
            "Optional path to staged pricing benchmark register JSON. "
            "When provided, PKG-020 register verification is enforced."
        ),
    )
    parser.add_argument(
        "--pricing-benchmark-register-required",
        action="store_true",
        help=(
            "Require pricing benchmark register verification. "
            "When set, --pricing-benchmark-register-path must be provided."
        ),
    )
    parser.add_argument(
        "--stress-max-age-hours",
        type=float,
        default=48.0,
        help="Maximum allowed age for stress evidence artifact in hours.",
    )
    parser.add_argument(
        "--failure-max-age-hours",
        type=float,
        default=48.0,
        help="Maximum allowed age for failure-injection evidence artifact in hours.",
    )
    parser.add_argument(
        "--finance-max-age-hours",
        type=float,
        default=744.0,
        help="Maximum allowed age for finance guardrails evidence artifact in hours.",
    )
    parser.add_argument(
        "--pricing-benchmark-max-source-age-days",
        type=float,
        default=120.0,
        help="Maximum allowed source age for pricing benchmark register entries in days.",
    )
    parser.add_argument(
        "--stress-min-duration-seconds",
        type=int,
        default=30,
        help="Minimum allowed duration_seconds for stress evidence verification.",
    )
    parser.add_argument(
        "--stress-min-concurrent-users",
        type=int,
        default=10,
        help="Minimum allowed concurrent_users for stress evidence verification.",
    )
    parser.add_argument(
        "--stress-required-database-engine",
        default="postgresql",
        help="Required DB backend captured in stress evidence runtime metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run enterprise gate in dry-run mode.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return run_release_gate(
        stress_evidence_path=Path(str(args.stress_evidence_path)),
        failure_evidence_path=Path(str(args.failure_evidence_path)),
        finance_evidence_path=(
            Path(str(args.finance_evidence_path))
            if args.finance_evidence_path
            else None
        ),
        finance_evidence_required=bool(args.finance_evidence_required),
        pricing_benchmark_register_path=(
            Path(str(args.pricing_benchmark_register_path))
            if args.pricing_benchmark_register_path
            else None
        ),
        pricing_benchmark_register_required=bool(
            args.pricing_benchmark_register_required
        ),
        stress_max_age_hours=float(args.stress_max_age_hours),
        failure_max_age_hours=float(args.failure_max_age_hours),
        finance_max_age_hours=float(args.finance_max_age_hours),
        pricing_benchmark_max_source_age_days=float(
            args.pricing_benchmark_max_source_age_days
        ),
        stress_min_duration_seconds=int(args.stress_min_duration_seconds),
        stress_min_concurrent_users=int(args.stress_min_concurrent_users),
        stress_required_database_engine=str(args.stress_required_database_engine),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
