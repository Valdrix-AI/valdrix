"""Verify each shared adapter module is referenced by at least one test."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_ADAPTERS_ROOT = Path("app/shared/adapters")
DEFAULT_TESTS_ROOT = Path("tests")
DEFAULT_ALLOWLIST: frozenset[str] = frozenset({"__init__"})


def _adapter_stems(adapters_root: Path) -> tuple[str, ...]:
    stems = [
        path.stem
        for path in adapters_root.glob("*.py")
        if path.stem not in DEFAULT_ALLOWLIST
    ]
    return tuple(sorted(stems))


def _collect_test_texts(tests_root: Path) -> tuple[tuple[Path, str], ...]:
    collected: list[tuple[Path, str]] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        if path.is_file():
            collected.append(
                (path, path.read_text(encoding="utf-8", errors="ignore"))
            )
    return tuple(collected)


def _is_adapter_referenced(stem: str, tests: tuple[tuple[Path, str], ...]) -> bool:
    dotted = f"app.shared.adapters.{stem}"
    import_from = f"from app.shared.adapters import {stem}"
    import_direct = f"import app.shared.adapters.{stem}"
    for path, text in tests:
        if stem in path.stem:
            return True
        if dotted in text or import_from in text or import_direct in text:
            return True
    return False


def find_uncovered_adapters(
    *,
    adapters_root: Path,
    tests_root: Path,
    allowlist: set[str] | None = None,
) -> tuple[str, ...]:
    effective_allowlist = set(DEFAULT_ALLOWLIST)
    effective_allowlist.update(allowlist or set())
    adapters = [
        stem
        for stem in _adapter_stems(adapters_root)
        if stem not in effective_allowlist
    ]
    tests = _collect_test_texts(tests_root)
    missing = [stem for stem in adapters if not _is_adapter_referenced(stem, tests)]
    return tuple(sorted(missing))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure each shared adapter module has at least one test reference."
    )
    parser.add_argument(
        "--adapters-root",
        type=Path,
        default=DEFAULT_ADAPTERS_ROOT,
        help="Directory containing adapter modules.",
    )
    parser.add_argument(
        "--tests-root",
        type=Path,
        default=DEFAULT_TESTS_ROOT,
        help="Directory containing pytest files.",
    )
    parser.add_argument(
        "--allowlist",
        action="append",
        default=[],
        help="Adapter module stem to exempt from reference checks (repeatable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    missing = find_uncovered_adapters(
        adapters_root=args.adapters_root,
        tests_root=args.tests_root,
        allowlist=set(args.allowlist),
    )
    if missing:
        print("[adapter-test-coverage] FAILED")
        for stem in missing:
            print(f"- missing test reference for adapter: {stem}")
        return 1

    print(
        "[adapter-test-coverage] ok "
        f"adapters_root={args.adapters_root.as_posix()} tests_root={args.tests_root.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

