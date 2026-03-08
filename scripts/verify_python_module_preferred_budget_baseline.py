#!/usr/bin/env python3
"""Track preferred-size Python module debt as a checked-in governance baseline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from scripts.verify_python_module_size_budget import (
    ModuleSizePreferredBreach,
    collect_module_size_preferred_breaches,
)


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_PATH = Path("docs/ops/evidence/python_module_size_preferred_baseline.json")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify preferred Python module-size breaches against a checked-in baseline."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root path.",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="Path to the preferred-size baseline JSON.",
    )
    parser.add_argument(
        "--preferred-max-lines",
        type=int,
        default=500,
        help="Preferred line budget used to collect current breaches.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Refresh the checked-in baseline from the current repository state.",
    )
    return parser.parse_args(argv)


def _load_baseline(path: Path) -> tuple[ModuleSizePreferredBreach, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[ModuleSizePreferredBreach] = []
    for raw in payload.get("breaches", []):
        if not isinstance(raw, dict):
            continue
        path_value = raw.get("path")
        lines = raw.get("lines")
        preferred = raw.get("preferred_max_lines")
        if (
            isinstance(path_value, str)
            and isinstance(lines, int)
            and isinstance(preferred, int)
        ):
            items.append(
                ModuleSizePreferredBreach(
                    path=path_value,
                    lines=lines,
                    preferred_max_lines=preferred,
                )
            )
    return tuple(sorted(items, key=lambda item: item.path))


def _write_baseline(
    *,
    path: Path,
    root: Path,
    breaches: tuple[ModuleSizePreferredBreach, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(root),
        "breaches": [asdict(item) for item in breaches],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _by_key(
    breaches: tuple[ModuleSizePreferredBreach, ...],
) -> dict[str, ModuleSizePreferredBreach]:
    return {item.path: item for item in breaches}


def verify_against_baseline(
    *,
    current: tuple[ModuleSizePreferredBreach, ...],
    baseline: tuple[ModuleSizePreferredBreach, ...],
) -> tuple[
    tuple[ModuleSizePreferredBreach, ...],
    tuple[ModuleSizePreferredBreach, ...],
    tuple[tuple[ModuleSizePreferredBreach, ModuleSizePreferredBreach], ...],
]:
    current_by_path = _by_key(current)
    baseline_by_path = _by_key(baseline)

    added = tuple(
        sorted(
            (
                breach
                for path, breach in current_by_path.items()
                if path not in baseline_by_path
            ),
            key=lambda item: item.path,
        )
    )
    removed = tuple(
        sorted(
            (
                breach
                for path, breach in baseline_by_path.items()
                if path not in current_by_path
            ),
            key=lambda item: item.path,
        )
    )
    changed = tuple(
        sorted(
            (
                (baseline_by_path[path], current_by_path[path])
                for path in current_by_path.keys() & baseline_by_path.keys()
                if current_by_path[path] != baseline_by_path[path]
            ),
            key=lambda item: item[0].path,
        )
    )
    return added, removed, changed


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    baseline_path = (
        args.baseline_path
        if args.baseline_path.is_absolute()
        else root / args.baseline_path
    )
    current = collect_module_size_preferred_breaches(
        root,
        preferred_max_lines=int(args.preferred_max_lines),
    )

    if args.write_baseline:
        _write_baseline(path=baseline_path, root=root, breaches=current)
        print(
            "Preferred module-size baseline refreshed "
            f"(breaches={len(current)}) -> {baseline_path.as_posix()}"
        )
        return 0

    if not baseline_path.exists():
        print(f"Missing preferred-size baseline: {baseline_path.as_posix()}")
        return 2

    baseline = _load_baseline(baseline_path)
    added, removed, changed = verify_against_baseline(
        current=current,
        baseline=baseline,
    )
    if added or removed or changed:
        print("Preferred module-size baseline drift detected:")
        for breach in added:
            print(
                f"- added: {breach.path} ({breach.lines} lines, preferred={breach.preferred_max_lines})"
            )
        for breach in removed:
            print(
                f"- removed: {breach.path} ({breach.lines} lines, preferred={breach.preferred_max_lines})"
            )
        for baseline_item, current_item in changed:
            print(
                f"- changed: {baseline_item.path} "
                f"(baseline={baseline_item.lines}, current={current_item.lines}, preferred={current_item.preferred_max_lines})"
            )
        return 1

    print(
        "Preferred module-size baseline check passed "
        f"(breaches={len(current)}, baseline={len(baseline)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
