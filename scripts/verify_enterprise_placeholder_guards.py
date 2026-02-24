"""Enforce no-placeholder/no-shim markers in enterprise hardening code paths."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_STRICT_SCAN_ROOTS: tuple[Path, ...] = (
    Path("app/modules/enforcement"),
    Path("app/models/enforcement.py"),
    Path("app/shared/core/turnstile.py"),
    Path("app/shared/llm/budget_fair_use.py"),
    Path("app/shared/llm/budget_execution.py"),
    Path("app/shared/llm/analyzer.py"),
    Path("app/shared/llm/zombie_analyzer.py"),
    Path("app/shared/llm/factory.py"),
    Path("app/shared/llm/providers/openai.py"),
    Path("app/shared/llm/providers/anthropic.py"),
    Path("app/shared/llm/providers/google.py"),
    Path("app/shared/llm/providers/groq.py"),
    Path("app/modules/reporting/api/v1/costs.py"),
    Path("app/shared/core/pricing.py"),
    Path("app/shared/core/config.py"),
)

DEFAULT_FULL_SCAN_ROOTS: tuple[Path, ...] = (
    Path("app"),
    Path("scripts"),
    Path("migrations"),
    Path("loadtest"),
)

DEFAULT_MARKER_PATTERNS: tuple[str, ...] = (
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bHACK\b",
    r"\bTEMP\b",
    r"NotImplementedError",
    r"legacy[ _-]?shim",
    r"backward[ _-]?compatibility",
)

DEFAULT_FILE_EXTENSIONS: tuple[str, ...] = (".py",)
DEFAULT_FULL_ALLOWLIST_FILE = Path("scripts/placeholder_guard_allowlist_full.txt")


@dataclass(frozen=True)
class MarkerViolation:
    path: str
    line_number: int
    pattern: str
    matched_text: str


@dataclass(frozen=True)
class AllowRule:
    path_regex: str
    marker_regex: str | None


def _iter_files(root: Path, allowed_extensions: set[str]) -> Iterable[Path]:
    if root.is_file():
        if root.suffix in allowed_extensions:
            yield root
        return

    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix in allowed_extensions:
            yield candidate


def _is_allowed_violation(violation: MarkerViolation, allow_rules: Sequence[AllowRule]) -> bool:
    for rule in allow_rules:
        if re.search(rule.path_regex, violation.path) is None:
            continue
        if rule.marker_regex is None:
            return True

        marker_regex = rule.marker_regex
        if re.search(marker_regex, violation.pattern, flags=re.IGNORECASE):
            return True
        if re.search(marker_regex, violation.matched_text, flags=re.IGNORECASE):
            return True
    return False


def scan_paths_for_disallowed_markers(
    *,
    roots: Sequence[Path],
    marker_patterns: Sequence[str],
    allowed_extensions: Sequence[str] = DEFAULT_FILE_EXTENSIONS,
    allow_rules: Sequence[AllowRule] = (),
) -> list[MarkerViolation]:
    compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in marker_patterns]
    extensions = set(allowed_extensions)
    violations: list[MarkerViolation] = []

    for root in roots:
        for file_path in _iter_files(root, extensions):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for pattern in compiled_patterns:
                    match = pattern.search(line)
                    if match is None:
                        continue
                    violation = MarkerViolation(
                        path=file_path.as_posix(),
                        line_number=line_number,
                        pattern=pattern.pattern,
                        matched_text=match.group(0),
                    )
                    if allow_rules and _is_allowed_violation(violation, allow_rules):
                        continue
                    violations.append(violation)

    return sorted(
        violations,
        key=lambda item: (item.path, item.line_number, item.pattern),
    )


def load_allow_rules(path: Path) -> list[AllowRule]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Allowlist file not found: {path.as_posix()}")

    rules: list[AllowRule] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        path_regex, sep, marker_regex = line.partition("::")
        normalized_path_regex = path_regex.strip()
        normalized_marker_regex = marker_regex.strip() if sep else ""
        if not normalized_path_regex:
            raise ValueError(
                f"Invalid allowlist entry at {path.as_posix()}:{line_number}: empty path regex"
            )

        # Validate regex eagerly to fail fast on malformed entries.
        re.compile(normalized_path_regex)
        if normalized_marker_regex:
            re.compile(normalized_marker_regex, flags=re.IGNORECASE)
            rules.append(
                AllowRule(
                    path_regex=normalized_path_regex,
                    marker_regex=normalized_marker_regex,
                )
            )
        else:
            rules.append(AllowRule(path_regex=normalized_path_regex, marker_regex=None))

    return rules


def _resolve_scan_roots(profile: str, explicit_roots: Sequence[str]) -> tuple[Path, ...]:
    if explicit_roots:
        return tuple(Path(item) for item in explicit_roots)
    if profile == "full":
        return DEFAULT_FULL_SCAN_ROOTS
    return DEFAULT_STRICT_SCAN_ROOTS


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail if code contains placeholder/legacy markers in strict enterprise paths "
            "or full-repository audit profile."
        )
    )
    parser.add_argument(
        "--profile",
        choices=("strict", "full"),
        default="strict",
        help="strict: enterprise control-plane hardening paths, full: repository audit paths.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Root path to scan (file or directory). "
            "If omitted, profile defaults are used."
        ),
    )
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="Additional disallowed marker regex pattern.",
    )
    parser.add_argument(
        "--allowlist-file",
        type=Path,
        default=None,
        help=(
            "Optional allowlist file. Format per line: <path_regex>::<marker_regex>. "
            "If marker regex is omitted, all markers for the matched path are allowed."
        ),
    )
    parser.add_argument(
        "--allow-missing-root",
        action="store_true",
        help="Skip missing roots instead of failing.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    roots = _resolve_scan_roots(args.profile, args.root)
    patterns = (
        tuple(DEFAULT_MARKER_PATTERNS) + tuple(args.pattern)
        if args.pattern
        else DEFAULT_MARKER_PATTERNS
    )

    allowlist_path: Path | None = args.allowlist_file
    if allowlist_path is None and args.profile == "full" and DEFAULT_FULL_ALLOWLIST_FILE.exists():
        allowlist_path = DEFAULT_FULL_ALLOWLIST_FILE

    allow_rules: list[AllowRule] = []
    if allowlist_path is not None:
        allow_rules = load_allow_rules(allowlist_path)

    missing_roots = [root for root in roots if not root.exists()]
    if missing_roots and not args.allow_missing_root:
        missing_text = ", ".join(path.as_posix() for path in missing_roots)
        print(f"Missing required scan root(s): {missing_text}")
        return 2

    available_roots = [root for root in roots if root.exists()]
    violations = scan_paths_for_disallowed_markers(
        roots=available_roots,
        marker_patterns=patterns,
        allow_rules=allow_rules,
    )

    if not violations:
        print(
            "No disallowed placeholder/legacy markers found "
            f"(profile={args.profile}, roots={len(available_roots)})."
        )
        return 0

    print("Disallowed markers detected:")
    for violation in violations:
        print(
            f"- {violation.path}:{violation.line_number} "
            f"[{violation.pattern}] -> {violation.matched_text}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
