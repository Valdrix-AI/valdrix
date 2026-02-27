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
    "tests/unit/shared/llm/test_budget_fair_use_branches.py",
    "tests/unit/shared/llm/test_budget_execution_branches.py",
    "tests/unit/shared/llm/test_budget_scheduler.py",
    "tests/unit/core/test_budget_manager_fair_use.py",
    "tests/unit/core/test_budget_manager_audit.py",
    "tests/unit/llm/test_budget_manager.py",
    "tests/unit/llm/test_budget_manager_exhaustive.py",
    "tests/unit/llm/test_factory_exhaustive.py",
    "tests/unit/llm/test_providers.py",
    "tests/unit/llm/test_usage_tracker.py",
    "tests/unit/llm/test_usage_tracker_audit.py",
    "tests/unit/llm/test_analyzer_exhaustive.py",
    "tests/unit/llm/test_analyzer_branch_edges.py",
    "tests/unit/api/v1/test_costs_endpoints.py",
    "tests/unit/api/v1/test_costs_acceptance_payload_branches.py",
    "tests/unit/api/v1/test_reconciliation_endpoints.py",
    "tests/unit/services/llm/test_llm_logic.py",
    "tests/unit/ops/test_enforcement_failure_injection_pack.py",
    "tests/unit/ops/test_enforcement_stress_evidence_pack.py",
    "tests/unit/ops/test_verify_enforcement_stress_evidence.py",
    "tests/unit/ops/test_verify_enforcement_post_closure_sanity.py",
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
