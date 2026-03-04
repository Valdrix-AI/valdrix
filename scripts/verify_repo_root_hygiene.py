"""Verify repository root hygiene for release automation."""

from __future__ import annotations

import argparse
import fnmatch
from dataclasses import dataclass
from pathlib import Path


PROHIBITED_ROOT_PATTERNS: tuple[str, ...] = (
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


@dataclass(frozen=True)
class RootHygieneViolation:
    name: str
    pattern: str


def collect_root_hygiene_violations(
    root: Path, *, prohibited_patterns: tuple[str, ...] = PROHIBITED_ROOT_PATTERNS
) -> tuple[RootHygieneViolation, ...]:
    violations: list[RootHygieneViolation] = []
    for child in root.iterdir():
        if not child.is_file():
            continue
        for pattern in prohibited_patterns:
            if fnmatch.fnmatch(child.name, pattern):
                violations.append(
                    RootHygieneViolation(name=child.name, pattern=pattern)
                )
                break
    return tuple(sorted(violations, key=lambda item: item.name))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail when prohibited artifacts are present in repository root."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root path (defaults to current repository).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    violations = collect_root_hygiene_violations(root)
    if not violations:
        print(f"[repo-root-hygiene] ok root={root}")
        return 0

    print(f"[repo-root-hygiene] found {len(violations)} prohibited root file(s):")
    for violation in violations:
        print(
            f" - {violation.name} (matched pattern {violation.pattern!r}); "
            "move to docs/ or remove from repository root."
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
