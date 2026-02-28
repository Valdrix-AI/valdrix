"""Run enterprise hardening TDD release gate commands in CI/local automation."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ENTERPRISE_GATE_TEST_TARGETS: tuple[str, ...] = (
    "tests/unit/enforcement",
    "tests/unit/api/v1/test_attribution_branch_paths.py",
    "tests/unit/api/v1/test_carbon.py",
    "tests/unit/api/v1/test_costs_metrics_branch_paths.py",
    "tests/unit/api/v1/test_currency_endpoints.py",
    "tests/unit/api/v1/test_leaderboards_endpoints.py",
    "tests/unit/api/v1/test_leadership_kpis_branch_paths.py",
    "tests/unit/api/v1/test_leadership_kpis_branch_paths_2.py",
    "tests/unit/api/v1/test_leadership_kpis_endpoints.py",
    "tests/unit/api/v1/test_savings_branch_paths.py",
    "tests/unit/api/v1/test_usage_endpoints.py",
    "tests/unit/api/v1/test_usage_branch_paths.py",
    "tests/unit/shared/llm/test_budget_fair_use_branches.py",
    "tests/unit/shared/llm/test_budget_execution_branches.py",
    "tests/unit/shared/llm/test_budget_scheduler.py",
    "tests/unit/shared/llm/test_pricing_data.py",
    "tests/unit/core/test_budget_manager_fair_use.py",
    "tests/unit/core/test_budget_manager_audit.py",
    "tests/unit/llm/test_circuit_breaker.py",
    "tests/unit/llm/test_delta_analysis.py",
    "tests/unit/llm/test_delta_analysis_branch_paths_2.py",
    "tests/unit/llm/test_delta_analysis_exhaustive.py",
    "tests/unit/llm/test_budget_manager.py",
    "tests/unit/llm/test_budget_manager_exhaustive.py",
    "tests/unit/llm/test_guardrails_audit.py",
    "tests/unit/llm/test_hybrid_scheduler.py",
    "tests/unit/llm/test_hybrid_scheduler_exhaustive.py",
    "tests/unit/llm/test_factory_exhaustive.py",
    "tests/unit/llm/test_providers.py",
    "tests/unit/llm/test_usage_tracker.py",
    "tests/unit/llm/test_usage_tracker_audit.py",
    "tests/unit/llm/test_zombie_analyzer.py",
    "tests/unit/llm/test_zombie_analyzer_exhaustive.py",
    "tests/unit/llm/test_analyzer_exhaustive.py",
    "tests/unit/llm/test_analyzer_branch_edges.py",
    "tests/unit/services/llm/test_guardrails_logic.py",
    "tests/unit/api/v1/test_costs_endpoints.py",
    "tests/unit/api/v1/test_costs_acceptance_payload_branches.py",
    "tests/unit/api/v1/test_reconciliation_endpoints.py",
    "tests/unit/services/llm/test_llm_logic.py",
    "tests/unit/ops/test_enforcement_failure_injection_pack.py",
    "tests/unit/ops/test_enforcement_stress_evidence_pack.py",
    "tests/unit/ops/test_key_rotation_drill_evidence_pack.py",
    "tests/unit/ops/test_verify_key_rotation_drill_evidence.py",
    "tests/unit/ops/test_verify_enforcement_failure_injection_evidence.py",
    "tests/unit/ops/test_verify_enforcement_stress_evidence.py",
    "tests/unit/ops/test_verify_enforcement_post_closure_sanity.py",
    "tests/unit/ops/test_verify_finance_guardrails_evidence.py",
    "tests/unit/ops/test_finance_guardrails_evidence_pack.py",
    "tests/unit/ops/test_verify_pricing_benchmark_register.py",
    "tests/unit/ops/test_pricing_benchmark_register_pack.py",
    "tests/unit/ops/test_release_artifact_templates_pack.py",
    "tests/unit/supply_chain/test_verify_jwt_bcp_checklist.py",
    "tests/unit/supply_chain/test_feature_enforceability_matrix.py",
    "tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py",
    "tests/contract/test_openapi_contract.py",
)

ENTERPRISE_GATE_COVERAGE_TARGETS: tuple[str, ...] = (
    "app/modules/enforcement",
    "app/shared/llm",
    "app/modules/reporting/api/v1",
)

ENFORCEMENT_COVERAGE_FAIL_UNDER = 95
LLM_COVERAGE_FAIL_UNDER = 90
ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER = 99

LLM_GUARDRAIL_COVERAGE_INCLUDE: tuple[str, ...] = (
    "app/shared/llm/budget_fair_use.py",
    "app/shared/llm/budget_execution.py",
    "app/shared/llm/budget_manager.py",
    "app/shared/llm/usage_tracker.py",
    "app/shared/llm/factory.py",
    "app/shared/llm/providers/openai.py",
    "app/shared/llm/providers/anthropic.py",
    "app/shared/llm/providers/google.py",
    "app/shared/llm/providers/groq.py",
)

ANALYTICS_VISIBILITY_COVERAGE_INCLUDE: tuple[str, ...] = (
    "app/shared/llm/analyzer.py",
    "app/modules/reporting/api/v1/costs.py",
)

ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV = "ENFORCEMENT_STRESS_EVIDENCE_PATH"
ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS_ENV = (
    "ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS"
)
ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_ENV = "ENFORCEMENT_STRESS_EVIDENCE_REQUIRED"
ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS_ENV = (
    "ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS"
)
ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS_ENV = (
    "ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS"
)
ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE_ENV = (
    "ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE"
)
DEFAULT_ENFORCEMENT_STRESS_MIN_DURATION_SECONDS = "30"
DEFAULT_ENFORCEMENT_STRESS_MIN_CONCURRENT_USERS = "10"
DEFAULT_ENFORCEMENT_STRESS_REQUIRED_DATABASE_ENGINE = "postgresql"
ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH_ENV = (
    "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH"
)
ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS_ENV = (
    "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS"
)
ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED_ENV = (
    "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED"
)
ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV = (
    "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH"
)
ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS_ENV = (
    "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS"
)
ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED_ENV = (
    "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED"
)
DEFAULT_ENFORCEMENT_FINANCE_GUARDRAILS_MAX_AGE_HOURS = "744"
ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV = (
    "ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH"
)
ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED_ENV = (
    "ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED"
)
ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS_ENV = (
    "ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS"
)
DEFAULT_ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS = "120"
ENFORCEMENT_KEY_ROTATION_DRILL_PATH_ENV = "ENFORCEMENT_KEY_ROTATION_DRILL_PATH"
ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS_ENV = (
    "ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS"
)
DEFAULT_KEY_ROTATION_DRILL_PATH = "docs/ops/key-rotation-drill-2026-02-27.md"
DEFAULT_KEY_ROTATION_DRILL_MAX_AGE_DAYS = "120"


@dataclass
class CoverageSubsetTotals:
    lines_valid: int = 0
    lines_covered: int = 0
    branches_valid: int = 0
    branches_covered: int = 0

    def percent(self) -> float:
        denominator = self.lines_valid + self.branches_valid
        if denominator <= 0:
            return 100.0
        numerator = self.lines_covered + self.branches_covered
        return (numerator / denominator) * 100.0


_COND_RE = re.compile(r"\((\d+)/(\d+)\)")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_xml_class_repo_path(
    *,
    filename: str,
    source_roots: tuple[Path, ...],
    repo_root: Path,
) -> str | None:
    for source_root in source_roots:
        candidate = source_root / filename
        if candidate.exists():
            return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
    return None


def _parse_condition_coverage(raw: str | None) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    match = _COND_RE.search(raw)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


def compute_coverage_subset_from_xml(
    *,
    xml_path: Path,
    include_patterns: Sequence[str],
    repo_root: Path,
) -> CoverageSubsetTotals:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    source_roots = tuple(
        Path(node.text)
        for node in root.findall("./sources/source")
        if node.text
    )
    totals = CoverageSubsetTotals()

    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename")
        if not filename:
            continue
        repo_path = _resolve_xml_class_repo_path(
            filename=filename,
            source_roots=source_roots,
            repo_root=repo_root,
        )
        if repo_path is None:
            continue
        if not any(fnmatch.fnmatch(repo_path, pattern) for pattern in include_patterns):
            continue

        lines_parent = class_node.find("./lines")
        if lines_parent is None:
            continue
        for line_node in lines_parent.findall("./line"):
            totals.lines_valid += 1
            hits = int(line_node.attrib.get("hits", "0"))
            if hits > 0:
                totals.lines_covered += 1
            if line_node.attrib.get("branch") == "true":
                covered, valid = _parse_condition_coverage(
                    line_node.attrib.get("condition-coverage")
                )
                totals.branches_covered += covered
                totals.branches_valid += valid

    return totals


def verify_coverage_subset_from_xml(
    *,
    xml_path: Path,
    include_patterns: Sequence[str],
    fail_under: int,
    label: str,
    repo_root: Path,
) -> None:
    if not xml_path.exists():
        raise RuntimeError(f"Coverage XML artifact missing: {xml_path}")
    totals = compute_coverage_subset_from_xml(
        xml_path=xml_path,
        include_patterns=include_patterns,
        repo_root=repo_root,
    )
    if (totals.lines_valid + totals.branches_valid) <= 0:
        raise RuntimeError(
            "Coverage XML subset matched no measurable lines/branches "
            f"for include patterns: {','.join(include_patterns)}"
        )
    percent = totals.percent()
    print(
        "[enterprise-gate] xml-coverage "
        f"{label}: {percent:.1f}% "
        f"(lines={totals.lines_covered}/{totals.lines_valid}, "
        f"branches={totals.branches_covered}/{totals.branches_valid})"
    )
    if percent + 1e-9 < float(fail_under):
        raise RuntimeError(
            f"Coverage failure ({label}): {percent:.1f}% < fail-under={fail_under}"
        )


def _parse_coverage_report_args(cmd: Sequence[str]) -> tuple[list[str], int] | None:
    if len(cmd) < 4 or list(cmd[:4]) != ["uv", "run", "coverage", "report"]:
        return None
    include_arg = next((arg for arg in cmd if arg.startswith("--include=")), None)
    fail_under_arg = next(
        (arg for arg in cmd if arg.startswith("--fail-under=")),
        None,
    )
    if include_arg is None or fail_under_arg is None:
        return None
    include_patterns = [
        part for part in include_arg.removeprefix("--include=").split(",") if part
    ]
    fail_under = int(fail_under_arg.removeprefix("--fail-under="))
    return (include_patterns, fail_under)


def _is_truthy(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def build_gate_commands() -> list[list[str]]:
    pytest_cmd: list[str] = ["uv", "run", "pytest", "-q", "-o", "addopts="]
    pytest_cmd.extend(ENTERPRISE_GATE_TEST_TARGETS)
    pytest_cmd.extend(
        f"--cov={target}" for target in ENTERPRISE_GATE_COVERAGE_TARGETS
    )
    pytest_cmd.extend(
        [
            "--cov-report=xml:coverage-enterprise-gate.xml",
            "--cov-report=term-missing",
        ]
    )

    commands: list[list[str]] = [
        [
            "uv",
            "run",
            "python3",
            "scripts/verify_jwt_bcp_checklist.py",
            "--checklist-path",
            "docs/security/jwt_bcp_checklist_2026-02-27.json",
        ],
        [
            "uv",
            "run",
            "python3",
            "scripts/verify_ssdf_traceability_matrix.py",
            "--matrix-path",
            "docs/security/ssdf_traceability_matrix_2026-02-25.json",
        ],
        [
            "uv",
            "run",
            "python3",
            "scripts/verify_enforcement_post_closure_sanity.py",
            "--doc-path",
            "docs/ops/enforcement_post_closure_sanity_2026-02-26.md",
            "--gap-register",
            "docs/ops/enforcement_control_plane_gap_register_2026-02-23.md",
        ],
        [
            "uv",
            "run",
            "python3",
            "scripts/verify_feature_enforceability_matrix.py",
            "--matrix-path",
            "docs/ops/feature_enforceability_matrix_2026-02-27.json",
        ],
    ]

    key_rotation_drill_path = (
        os.getenv(ENFORCEMENT_KEY_ROTATION_DRILL_PATH_ENV, "").strip()
        or DEFAULT_KEY_ROTATION_DRILL_PATH
    )
    key_rotation_max_age_days = (
        os.getenv(ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS_ENV, "").strip()
        or DEFAULT_KEY_ROTATION_DRILL_MAX_AGE_DAYS
    )
    commands.append(
        [
            "uv",
            "run",
            "python3",
            "scripts/verify_key_rotation_drill_evidence.py",
            "--drill-path",
            key_rotation_drill_path,
            "--max-drill-age-days",
            key_rotation_max_age_days,
        ]
    )

    stress_evidence_path = os.getenv(ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV, "").strip()
    stress_evidence_required = _is_truthy(
        os.getenv(ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_ENV)
    )
    if stress_evidence_required and not stress_evidence_path:
        raise ValueError(
            "ENFORCEMENT_STRESS_EVIDENCE_REQUIRED is true but "
            "ENFORCEMENT_STRESS_EVIDENCE_PATH is not set"
        )
    if stress_evidence_path:
        stress_min_duration_seconds = (
            os.getenv(ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS_ENV, "").strip()
            or DEFAULT_ENFORCEMENT_STRESS_MIN_DURATION_SECONDS
        )
        stress_min_concurrent_users = (
            os.getenv(ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS_ENV, "").strip()
            or DEFAULT_ENFORCEMENT_STRESS_MIN_CONCURRENT_USERS
        )
        stress_required_database_engine = (
            os.getenv(
                ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE_ENV, ""
            ).strip()
            or DEFAULT_ENFORCEMENT_STRESS_REQUIRED_DATABASE_ENGINE
        )
        stress_cmd = [
            "uv",
            "run",
            "python3",
            "scripts/verify_enforcement_stress_evidence.py",
            "--evidence-path",
            stress_evidence_path,
            "--min-duration-seconds",
            stress_min_duration_seconds,
            "--min-concurrent-users",
            stress_min_concurrent_users,
            "--required-database-engine",
            stress_required_database_engine,
        ]
        stress_artifact_max_age = os.getenv(
            ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS_ENV, ""
        ).strip()
        if stress_artifact_max_age:
            stress_cmd.extend(
                [
                    "--max-artifact-age-hours",
                    stress_artifact_max_age,
                ]
            )
        commands.append(stress_cmd)

    failure_injection_evidence_path = os.getenv(
        ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH_ENV, ""
    ).strip()
    failure_injection_evidence_required = _is_truthy(
        os.getenv(ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED_ENV)
    )
    if failure_injection_evidence_required and not failure_injection_evidence_path:
        raise ValueError(
            "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED is true but "
            "ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH is not set"
        )
    if failure_injection_evidence_path:
        failure_injection_cmd = [
            "uv",
            "run",
            "python3",
            "scripts/verify_enforcement_failure_injection_evidence.py",
            "--evidence-path",
            failure_injection_evidence_path,
        ]
        failure_injection_max_age = os.getenv(
            ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS_ENV, ""
        ).strip()
        if failure_injection_max_age:
            failure_injection_cmd.extend(
                [
                    "--max-artifact-age-hours",
                    failure_injection_max_age,
                ]
            )
        commands.append(failure_injection_cmd)

    finance_evidence_path = os.getenv(
        ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV, ""
    ).strip()
    finance_evidence_required = _is_truthy(
        os.getenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED_ENV)
    )
    if finance_evidence_required and not finance_evidence_path:
        raise ValueError(
            "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED is true but "
            "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH is not set"
        )
    if finance_evidence_path:
        finance_max_age_hours = (
            os.getenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS_ENV, "").strip()
            or DEFAULT_ENFORCEMENT_FINANCE_GUARDRAILS_MAX_AGE_HOURS
        )
        commands.append(
            [
                "uv",
                "run",
                "python3",
                "scripts/verify_finance_guardrails_evidence.py",
                "--evidence-path",
                finance_evidence_path,
                "--max-artifact-age-hours",
                finance_max_age_hours,
            ]
        )

    pricing_benchmark_register_path = os.getenv(
        ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV, ""
    ).strip()
    pricing_benchmark_register_required = _is_truthy(
        os.getenv(ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED_ENV)
    )
    if pricing_benchmark_register_required and not pricing_benchmark_register_path:
        raise ValueError(
            "ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED is true but "
            "ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH is not set"
        )
    if pricing_benchmark_register_path:
        pricing_max_source_age_days = (
            os.getenv(
                ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS_ENV, ""
            ).strip()
            or DEFAULT_ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS
        )
        commands.append(
            [
                "uv",
                "run",
                "python3",
                "scripts/verify_pricing_benchmark_register.py",
                "--register-path",
                pricing_benchmark_register_path,
                "--max-source-age-days",
                pricing_max_source_age_days,
            ]
        )

    commands.extend(
        [
            [
                "uv",
                "run",
                "python3",
                "scripts/verify_enterprise_placeholder_guards.py",
                "--profile",
                "strict",
            ],
            pytest_cmd,
            [
                "uv",
                "run",
                "coverage",
                "report",
                '--include=app/modules/enforcement/*',
                f"--fail-under={ENFORCEMENT_COVERAGE_FAIL_UNDER}",
            ],
            [
                "uv",
                "run",
                "coverage",
                "report",
                f"--include={','.join(LLM_GUARDRAIL_COVERAGE_INCLUDE)}",
                f"--fail-under={LLM_COVERAGE_FAIL_UNDER}",
            ],
            [
                "uv",
                "run",
                "coverage",
                "report",
                f"--include={','.join(ANALYTICS_VISIBILITY_COVERAGE_INCLUDE)}",
                f"--fail-under={ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER}",
            ],
        ]
    )
    return commands


def _format_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_gate(*, dry_run: bool) -> int:
    commands = build_gate_commands()
    repo_root = _repo_root()
    coverage_xml_path = repo_root / "coverage-enterprise-gate.xml"
    coverage_data_path = repo_root / ".coverage.enterprise-gate"
    if not dry_run:
        coverage_data_path.unlink(missing_ok=True)
    command_env = os.environ.copy()
    command_env["COVERAGE_FILE"] = str(coverage_data_path)
    # Enforce deterministic release-gate behavior regardless of ambient shell values.
    # Some local profiles export non-boolean DEBUG values (for example "release"),
    # which can break pydantic settings parsing in pytest bootstrap.
    command_env["DEBUG"] = "false"
    for cmd in commands:
        rendered = _format_command(cmd)
        print(f"[enterprise-gate] {rendered}")
        if dry_run:
            continue
        try:
            subprocess.run(cmd, check=True, env=command_env)
        except subprocess.CalledProcessError:
            coverage_args = _parse_coverage_report_args(cmd)
            if coverage_args is None:
                raise
            include_patterns, fail_under = coverage_args
            label = ",".join(include_patterns)
            verify_coverage_subset_from_xml(
                xml_path=coverage_xml_path,
                include_patterns=include_patterns,
                fail_under=fail_under,
                label=label,
                repo_root=repo_root,
            )
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run enterprise hardening TDD release-blocking gate."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return run_gate(dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
