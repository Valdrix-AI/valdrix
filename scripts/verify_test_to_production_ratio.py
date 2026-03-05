"""Verify test-to-production Python line ratio stays within governance budget.

The ratio is computed from semantic Python lines:
- blank lines are excluded
- comment-only lines are excluded
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PRODUCTION_ROOTS: tuple[Path, ...] = (Path("app"), Path("scripts"))
DEFAULT_TESTS_ROOT = Path("tests")
DEFAULT_MAX_TEST_TO_PRODUCTION_RATIO = 1.20


@dataclass(frozen=True)
class RatioMetrics:
    production_lines: int
    test_lines: int

    @property
    def ratio(self) -> float:
        if self.production_lines <= 0:
            return 0.0
        return self.test_lines / self.production_lines


def _count_python_lines(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                total += 1
    return total


def compute_ratio_metrics(
    *, production_roots: tuple[Path, ...], tests_root: Path
) -> RatioMetrics:
    production_total = sum(_count_python_lines(root) for root in production_roots)
    return RatioMetrics(
        production_lines=production_total,
        test_lines=_count_python_lines(tests_root),
    )


def validate_ratio(
    *,
    production_roots: tuple[Path, ...],
    tests_root: Path,
    max_ratio: float = DEFAULT_MAX_TEST_TO_PRODUCTION_RATIO,
) -> tuple[RatioMetrics, tuple[str, ...]]:
    metrics = compute_ratio_metrics(
        production_roots=production_roots,
        tests_root=tests_root,
    )
    errors: list[str] = []
    if metrics.production_lines <= 0:
        errors.append("production code root contains no measurable Python lines")
        return metrics, tuple(errors)
    if metrics.ratio > max_ratio:
        errors.append(
            "test-to-production ratio exceeds budget: "
            f"{metrics.ratio:.2f}:1 > {max_ratio:.2f}:1"
        )
    return metrics, tuple(errors)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when Python test-to-production line ratio exceeds governance budget."
        )
    )
    parser.add_argument(
        "--production-root",
        type=Path,
        action="append",
        default=None,
        help=(
            "Root containing production Python modules. Repeatable; defaults to "
            "`app` and `scripts`."
        ),
    )
    parser.add_argument(
        "--tests-root",
        type=Path,
        default=DEFAULT_TESTS_ROOT,
        help="Root containing Python tests.",
    )
    parser.add_argument(
        "--max-ratio",
        type=float,
        default=DEFAULT_MAX_TEST_TO_PRODUCTION_RATIO,
        help="Maximum allowed tests-to-production ratio.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    production_roots = (
        tuple(args.production_root)
        if args.production_root
        else DEFAULT_PRODUCTION_ROOTS
    )
    metrics, errors = validate_ratio(
        production_roots=production_roots,
        tests_root=args.tests_root,
        max_ratio=float(args.max_ratio),
    )
    roots_text = ",".join(root.as_posix() for root in production_roots)
    ratio_text = f"{metrics.ratio:.2f}:1"
    if errors:
        print("[test-prod-ratio] FAILED")
        print(
            "[test-prod-ratio] "
            f"production_roots={roots_text} "
            f"production_lines={metrics.production_lines} "
            f"test_lines={metrics.test_lines} ratio={ratio_text} "
            f"max_ratio={float(args.max_ratio):.2f}:1"
        )
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "[test-prod-ratio] ok "
        f"production_roots={roots_text} "
        f"production_lines={metrics.production_lines} "
        f"test_lines={metrics.test_lines} ratio={ratio_text} "
        f"max_ratio={float(args.max_ratio):.2f}:1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
