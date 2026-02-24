"""Run enterprise hardening TDD release gate commands in CI/local automation."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from collections.abc import Sequence

ENTERPRISE_GATE_TEST_TARGETS: tuple[str, ...] = (
    "tests/unit/enforcement",
    "tests/unit/shared/llm/test_budget_fair_use_branches.py",
    "tests/unit/core/test_budget_manager_fair_use.py",
    "tests/unit/llm/test_budget_manager.py",
    "tests/unit/llm/test_budget_manager_exhaustive.py",
    "tests/unit/llm/test_factory_exhaustive.py",
    "tests/unit/llm/test_providers.py",
    "tests/unit/llm/test_analyzer_exhaustive.py",
    "tests/unit/api/v1/test_costs_endpoints.py",
    "tests/unit/services/llm/test_llm_logic.py",
    "tests/unit/shared/llm/test_budget_scheduler.py",
    "tests/contract/test_openapi_contract.py",
)

ENTERPRISE_GATE_COVERAGE_TARGETS: tuple[str, ...] = (
    "app/modules/enforcement",
    "app/shared/llm/budget_fair_use.py",
    "app/shared/llm/budget_execution.py",
    "app/shared/llm/analyzer.py",
    "app/shared/llm/factory.py",
    "app/shared/llm/providers/openai.py",
    "app/shared/llm/providers/anthropic.py",
    "app/shared/llm/providers/google.py",
    "app/shared/llm/providers/groq.py",
    "app/modules/reporting/api/v1/costs.py",
)

ENFORCEMENT_COVERAGE_FAIL_UNDER = 95
LLM_COVERAGE_FAIL_UNDER = 90


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

    return [
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
            '--include=app/shared/llm/*',
            f"--fail-under={LLM_COVERAGE_FAIL_UNDER}",
        ],
    ]


def _format_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_gate(*, dry_run: bool) -> int:
    commands = build_gate_commands()
    for cmd in commands:
        rendered = _format_command(cmd)
        print(f"[enterprise-gate] {rendered}")
        if dry_run:
            continue
        subprocess.run(cmd, check=True)
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
