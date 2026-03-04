"""Validate resolved audit findings against enforceable repository controls."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from scripts.verify_adapter_test_coverage import find_uncovered_adapters
from scripts.verify_exception_governance import collect_exception_sites
from scripts.verify_python_module_size_budget import DEFAULT_MAX_LINES

DEFAULT_REPORT_PATH = Path(
    "/home/daretechie/.gemini/antigravity/brain/"
    "dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved"
)
REPORT_FINDING_PATTERN = re.compile(r"^###\s+([CHML]-\d{2}):", re.MULTILINE)

FINDING_ORDER: tuple[str, ...] = (
    "C-01",
    "C-02",
    "C-03",
    "H-01",
    "H-02",
    "H-03",
    "H-04",
    "H-05",
    "H-06",
    "H-07",
    "H-08",
    "M-01",
    "M-02",
    "M-03",
    "M-04",
    "M-05",
    "M-06",
    "M-07",
    "M-08",
    "M-09",
    "M-10",
    "L-01",
    "L-02",
    "L-03",
    "L-04",
    "L-05",
    "L-06",
)

ROOT_PROHIBITED_PATTERNS: tuple[str, ...] = (
    "artifact.json",
    "codealike.json",
    "coverage-enterprise-gate.xml",
    "inspect_httpx.py",
    "full_test_output.log",
    "test_results.log",
    "feedback.md",
    "useLanding.md",
    "test_*.sqlite",
    "test_*.sqlite-shm",
    "test_*.sqlite-wal",
)

PERSONAL_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
    }
)


@dataclass(frozen=True)
class FindingDefinition:
    finding_id: str
    title: str
    check: Callable[[Path], tuple[str, ...]]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
            cleaned = cleaned[1:-1].strip()
        values[key] = cleaned
    return values


def _is_git_tracked(repo_root: Path, path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _check_env_pool_values(env_values: dict[str, str]) -> tuple[str, ...]:
    errors: list[str] = []
    for key in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT"):
        raw = env_values.get(key)
        if raw is None:
            errors.append(f"missing required env key: {key}")
            continue
        try:
            parsed = int(raw)
        except ValueError:
            errors.append(f"{key} must be integer (found {raw!r})")
            continue
        if parsed <= 0:
            errors.append(f"{key} must be > 0 (found {parsed})")
    return tuple(errors)


def _check_root_file_absent(repo_root: Path, pattern: str) -> tuple[str, ...]:
    for child in repo_root.iterdir():
        if not child.is_file():
            continue
        if fnmatch.fnmatch(child.name, pattern):
            return (f"root file must be absent for pattern {pattern!r}",)
    return ()


def _check_root_hygiene(repo_root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    for child in repo_root.iterdir():
        if not child.is_file():
            continue
        for pattern in ROOT_PROHIBITED_PATTERNS:
            if fnmatch.fnmatch(child.name, pattern):
                errors.append(f"prohibited root artifact: {child.name} (pattern={pattern})")
                break
    return tuple(errors)


def _check_c01(repo_root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    if _is_git_tracked(repo_root, ".env"):
        errors.append("`.env` is git-tracked; secrets must never be committed.")
    template_path = repo_root / ".env.example"
    if not template_path.exists():
        return ("missing .env.example template",)
    env_template = _parse_env(template_path)
    if env_template.get("CSRF_SECRET_KEY", "").strip():
        errors.append("CSRF_SECRET_KEY in .env.example must be empty.")
    return tuple(errors)


def _check_c02(repo_root: Path) -> tuple[str, ...]:
    template_path = repo_root / ".env.example"
    if not template_path.exists():
        return ("missing .env.example template",)
    env_template = _parse_env(template_path)
    smtp_user = env_template.get("SMTP_USER", "").strip()
    errors: list[str] = []
    if smtp_user:
        errors.append("SMTP_USER in .env.example must be empty.")
        if "@" in smtp_user:
            domain = smtp_user.rsplit("@", 1)[-1].lower()
            if domain in PERSONAL_EMAIL_DOMAINS:
                errors.append(f"personal email domain forbidden for SMTP_USER: {domain}")
    return tuple(errors)


def _check_c03(repo_root: Path) -> tuple[str, ...]:
    target = repo_root / "app/modules/enforcement/domain/service.py"
    if not target.exists():
        return (f"missing file: {target.as_posix()}",)
    lines = _line_count(target)
    if lines > DEFAULT_MAX_LINES:
        return (f"{target.as_posix()} is {lines} lines (budget={DEFAULT_MAX_LINES})",)
    return ()


def _check_h01(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "test_*.sqlite*")


def _check_h02(repo_root: Path) -> tuple[str, ...]:
    scan_roots = tuple(
        path for path in (repo_root / "app", repo_root / "scripts") if path.exists()
    )
    sites = collect_exception_sites(roots=scan_roots)
    if not sites:
        return ()
    preview = ", ".join(site.key() for site in sites[:5])
    return (f"catch-all handlers must be zero; found {len(sites)} ({preview})",)


def _check_h03(repo_root: Path) -> tuple[str, ...]:
    template_path = repo_root / ".env.example"
    if not template_path.exists():
        return ("missing .env.example template",)
    env_template = _parse_env(template_path)
    errors: list[str] = []
    if env_template.get("APP_NAME", "").strip() != "Valdrics":
        errors.append("APP_NAME in .env.example must be exactly `Valdrics`.")
    cloudformation_url = env_template.get("CLOUDFORMATION_TEMPLATE_URL", "")
    if "valdrix" in cloudformation_url.lower():
        errors.append("CLOUDFORMATION_TEMPLATE_URL references old `valdrix` branding.")
    return tuple(errors)


def _check_h04(repo_root: Path) -> tuple[str, ...]:
    budgets: dict[str, int] = {
        "app/modules/reporting/api/v1/costs.py": 1000,
        "app/modules/governance/api/v1/scim.py": 1000,
        "app/shared/core/notifications.py": 1000,
        "app/modules/governance/api/v1/settings/identity.py": 1000,
    }
    errors: list[str] = []
    for relative, max_lines in budgets.items():
        path = repo_root / relative
        if not path.exists():
            errors.append(f"missing file: {relative}")
            continue
        lines = _line_count(path)
        if lines > max_lines:
            errors.append(f"{relative} is {lines} lines (budget={max_lines})")
    return tuple(errors)


def _check_h05(repo_root: Path) -> tuple[str, ...]:
    template_path = repo_root / ".env.example"
    if not template_path.exists():
        return ("missing .env.example template",)
    return _check_env_pool_values(_parse_env(template_path))


def _check_h06(repo_root: Path) -> tuple[str, ...]:
    workflow_path = repo_root / ".github/workflows/ci.yml"
    if not workflow_path.exists():
        return ("missing CI workflow .github/workflows/ci.yml",)
    workflow = _read_text(workflow_path)
    required = (
        "uv run alembic upgrade head",
        "uv run alembic downgrade -1",
    )
    missing = [command for command in required if command not in workflow]
    if missing:
        return tuple(f"missing migration CI command: {command}" for command in missing)
    if workflow.count("uv run alembic upgrade head") < 2:
        return ("CI must run alembic upgrade head before and after downgrade.",)
    return ()


def _check_h07(repo_root: Path) -> tuple[str, ...]:
    gate_path = repo_root / "scripts/run_enterprise_tdd_gate.py"
    if not gate_path.exists():
        return ("missing enterprise gate runner script",)
    gate_text = _read_text(gate_path)
    required_tokens = (
        "--cov-report=xml:coverage-enterprise-gate.xml",
        "verify_coverage_subset_from_xml",
    )
    missing = [token for token in required_tokens if token not in gate_text]
    return tuple(f"missing coverage-governance token: {token}" for token in missing)


def _check_h08(repo_root: Path) -> tuple[str, ...]:
    target = repo_root / "app/tasks/scheduler_tasks.py"
    if not target.exists():
        return (f"missing file: {target.as_posix()}",)
    lines = _line_count(target)
    if lines > DEFAULT_MAX_LINES:
        return (f"{target.as_posix()} is {lines} lines (budget={DEFAULT_MAX_LINES})",)
    return ()


def _check_m01(repo_root: Path) -> tuple[str, ...]:
    gate_path = repo_root / "scripts/verify_python_module_size_budget.py"
    if not gate_path.exists():
        return ("missing module-size governance script",)
    text = _read_text(gate_path)
    if "DEFAULT_MAX_LINES = 600" not in text:
        return ("default module-size budget must remain 600 lines.",)
    return ()


def _check_m02(repo_root: Path) -> tuple[str, ...]:
    missing = find_uncovered_adapters(
        adapters_root=repo_root / "app/shared/adapters",
        tests_root=repo_root / "tests",
    )
    if not missing:
        return ()
    return tuple(f"adapter missing test reference: {name}" for name in missing)


def _check_m03(repo_root: Path) -> tuple[str, ...]:
    target = repo_root / "app/modules/governance/domain/security/compliance_pack_bundle.py"
    if not target.exists():
        return (f"missing file: {target.as_posix()}",)
    lines = _line_count(target)
    if lines > 1000:
        return (f"{target.as_posix()} is {lines} lines (budget=1000)",)
    return ()


def _check_m04(repo_root: Path) -> tuple[str, ...]:
    target = repo_root / "app/py.typed"
    if not target.exists():
        return ("missing app/py.typed marker file",)
    return ()


def _check_m05(repo_root: Path) -> tuple[str, ...]:
    return _check_h03(repo_root)


def _check_m06(repo_root: Path) -> tuple[str, ...]:
    workflow_path = repo_root / ".github/workflows/ci.yml"
    if not workflow_path.exists():
        return ("missing CI workflow .github/workflows/ci.yml",)
    workflow = _read_text(workflow_path).lower()
    required_tokens = ("aquasecurity/trivy-action", "trivy")
    missing = [token for token in required_tokens if token not in workflow]
    return tuple(f"missing CVE scanning token: {token}" for token in missing)


def _check_m07(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "inspect_httpx.py")


def _check_m08(repo_root: Path) -> tuple[str, ...]:
    target = repo_root / "docs/architecture/database_schema_overview.md"
    if not target.exists():
        return ("missing schema documentation: docs/architecture/database_schema_overview.md",)
    return ()


def _check_m09(repo_root: Path) -> tuple[str, ...]:
    path = repo_root / "app/shared/llm/analyzer.py"
    if not path.exists():
        return (f"missing file: {path.as_posix()}",)
    lines = _line_count(path)
    text = _read_text(path)
    errors: list[str] = []
    if lines > 1000:
        errors.append(f"{path.as_posix()} is {lines} lines (budget=1000)")
    required_tokens = (
        "FINOPS_ANALYSIS_SCHEMA_VERSION",
        "FINOPS_PROMPT_FALLBACK_VERSION",
        "FINOPS_RESPONSE_NORMALIZER_VERSION",
        "LLMGuardrails.validate_output",
        "prompt_version",
    )
    for token in required_tokens:
        if token not in text:
            errors.append(f"analyzer missing required governance token: {token}")
    return tuple(errors)


def _check_m10(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "feedback.md")


def _check_l01(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "artifact.json")


def _check_l02(repo_root: Path) -> tuple[str, ...]:
    duplicates = (
        "scripts/check_db.py",
        "scripts/check_db_tables.py",
        "scripts/db_check.py",
        "scripts/db_deep_dive.py",
        "scripts/analyze_tables.py",
    )
    errors: list[str] = []
    for duplicate in duplicates:
        if (repo_root / duplicate).exists():
            errors.append(f"duplicate DB diagnostic script must be removed: {duplicate}")
    if not (repo_root / "scripts/db_diagnostics.py").exists():
        errors.append("missing canonical DB diagnostics entrypoint: scripts/db_diagnostics.py")
    return tuple(errors)


def _check_l03(repo_root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    if (repo_root / "codealike.json").exists():
        errors.append("codealike.json must not exist in repository root.")
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        errors.append("missing .gitignore")
    elif "codealike.json" not in _read_text(gitignore):
        errors.append(".gitignore must include `codealike.json`.")
    return tuple(errors)


def _check_l04(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "useLanding.md")


def _check_l05(repo_root: Path) -> tuple[str, ...]:
    errors = list(_check_root_file_absent(repo_root, "full_test_output.log"))
    errors.extend(_check_root_file_absent(repo_root, "test_results.log"))
    return tuple(errors)


def _check_l06(repo_root: Path) -> tuple[str, ...]:
    return _check_root_file_absent(repo_root, "coverage-enterprise-gate.xml")


FINDING_DEFINITIONS: tuple[FindingDefinition, ...] = (
    FindingDefinition("C-01", "CSRF secret committed in .env", _check_c01),
    FindingDefinition("C-02", "Personal SMTP config", _check_c02),
    FindingDefinition("C-03", "God-object enforcement service", _check_c03),
    FindingDefinition("H-01", "Orphaned sqlite artifacts", _check_h01),
    FindingDefinition("H-02", "Broad catch-all exception usage", _check_h02),
    FindingDefinition("H-03", "Old branding in environment config", _check_h03),
    FindingDefinition("H-04", "Oversized API controller modules", _check_h04),
    FindingDefinition("H-05", "Missing DB pool controls", _check_h05),
    FindingDefinition("H-06", "Migration rollback CI guard", _check_h06),
    FindingDefinition("H-07", "Coverage governance signal", _check_h07),
    FindingDefinition("H-08", "Oversized scheduler tasks module", _check_h08),
    FindingDefinition("M-01", "Optimization scope guardrail", _check_m01),
    FindingDefinition("M-02", "Adapter test coverage unknown", _check_m02),
    FindingDefinition("M-03", "Oversized compliance bundle", _check_m03),
    FindingDefinition("M-04", "Missing py.typed marker", _check_m04),
    FindingDefinition("M-05", "Old branding template URL", _check_m05),
    FindingDefinition("M-06", "Missing image CVE scan", _check_m06),
    FindingDefinition("M-07", "Debug utility in repository root", _check_m07),
    FindingDefinition("M-08", "Missing schema documentation", _check_m08),
    FindingDefinition("M-09", "LLM analyzer governance controls", _check_m09),
    FindingDefinition("M-10", "Feedback artifact in repository root", _check_m10),
    FindingDefinition("L-01", "artifact.json root debris", _check_l01),
    FindingDefinition("L-02", "Database diagnostics script duplication", _check_l02),
    FindingDefinition("L-03", "codealike root artifact", _check_l03),
    FindingDefinition("L-04", "useLanding root artifact", _check_l04),
    FindingDefinition("L-05", "committed test output logs", _check_l05),
    FindingDefinition("L-06", "coverage artifact in root", _check_l06),
)

FINDING_INDEX: dict[str, FindingDefinition] = {
    definition.finding_id: definition for definition in FINDING_DEFINITIONS
}


def parse_report_findings(report_path: Path) -> tuple[str, ...]:
    text = _read_text(report_path)
    return tuple(REPORT_FINDING_PATTERN.findall(text))


def validate_report_scope(
    *,
    report_findings: tuple[str, ...],
    expected_findings: tuple[str, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    report_set = set(report_findings)
    expected_set = set(expected_findings)
    missing = sorted(expected_set - report_set)
    if missing:
        errors.append(
            "report missing expected finding headings: " + ", ".join(missing)
        )
    return tuple(errors)


def run_checks(
    *,
    repo_root: Path,
    finding_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    passes: list[str] = []

    root_hygiene_errors = _check_root_hygiene(repo_root)
    if root_hygiene_errors:
        failures.extend(f"[root-hygiene] {error}" for error in root_hygiene_errors)

    for finding_id in finding_ids:
        definition = FINDING_INDEX[finding_id]
        errors = definition.check(repo_root)
        if errors:
            failures.extend(f"[{finding_id}] {error}" for error in errors)
            continue
        passes.append(finding_id)
    return tuple(failures), tuple(passes)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate resolved audit findings against repository controls."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path to the markdown audit report to validate (can be outside repo).",
    )
    parser.add_argument(
        "--allow-missing-report",
        action="store_true",
        help="Do not fail when --report-path does not exist.",
    )
    parser.add_argument(
        "--skip-report-check",
        action="store_true",
        help="Skip parsing/validating report headings and run controls only.",
    )
    parser.add_argument(
        "--finding",
        action="append",
        default=[],
        help="Restrict checks to specific finding id(s), e.g. --finding C-01.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    selected = tuple(args.finding) if args.finding else FINDING_ORDER
    unknown = [finding for finding in selected if finding not in FINDING_INDEX]
    if unknown:
        print("Unknown finding id(s): " + ", ".join(sorted(unknown)))
        return 2

    report_errors: list[str] = []
    if not args.skip_report_check:
        report_path = args.report_path
        if not report_path.exists():
            if not args.allow_missing_report:
                print(
                    f"[audit-report] missing report file: {report_path.as_posix()} "
                    "(pass --allow-missing-report to continue without heading validation)."
                )
                return 2
            report_errors.append(
                f"report not found (skipped heading validation): {report_path.as_posix()}"
            )
        else:
            report_findings = parse_report_findings(report_path)
            report_errors.extend(
                validate_report_scope(
                    report_findings=report_findings,
                    expected_findings=selected,
                )
            )

    failures, passes = run_checks(repo_root=repo_root, finding_ids=selected)
    if report_errors:
        failures = tuple(f"[report] {error}" for error in report_errors) + failures

    if failures:
        print("[audit-report] FAILED")
        for failure in failures:
            print(f"- {failure}")
        print(
            f"[audit-report] summary passed={len(passes)} failed={len(failures)} "
            f"checked={len(selected)}"
        )
        return 1

    print(
        "[audit-report] ok "
        f"passed={len(passes)} checked={len(selected)} repo_root={repo_root.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
