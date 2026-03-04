"""Govern catch-all exception usage in production code paths."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROOTS: tuple[Path, ...] = (Path("app"), Path("scripts"))
DEFAULT_BASELINE_PATH = Path("docs/ops/evidence/exception_governance_baseline.json")


@dataclass(frozen=True)
class ExceptionSite:
    path: str
    line: int
    kind: str

    def key(self) -> str:
        return f"{self.path}:{self.line}:{self.kind}"


def _iter_python_files(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".py":
        yield root
        return
    for candidate in root.rglob("*.py"):
        if candidate.is_file():
            yield candidate


def _type_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _catch_kind(handler_type: ast.expr | None) -> str | None:
    if handler_type is None:
        return "bare_except"

    if isinstance(handler_type, ast.Tuple):
        names = {_type_name(item) for item in handler_type.elts}
        if "BaseException" in names:
            return "tuple_baseexception"
        if "Exception" in names:
            return "tuple_exception"
        return None

    name = _type_name(handler_type)
    if name == "BaseException":
        return "baseexception"
    if name == "Exception":
        return "exception"
    return None


def collect_exception_sites(*, roots: tuple[Path, ...]) -> tuple[ExceptionSite, ...]:
    sites: list[ExceptionSite] = []
    for root in roots:
        for path in _iter_python_files(root):
            raw = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(raw, filename=path.as_posix())
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                kind = _catch_kind(node.type)
                if kind is None:
                    continue
                sites.append(
                    ExceptionSite(
                        path=path.as_posix(),
                        line=int(node.lineno),
                        kind=kind,
                    )
                )
    return tuple(sorted(sites, key=lambda item: (item.path, item.line, item.kind)))


def write_baseline(
    *,
    baseline_path: Path,
    roots: tuple[Path, ...],
    sites: tuple[ExceptionSite, ...],
) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "roots": [root.as_posix() for root in roots],
        "sites": [asdict(site) for site in sites],
    }
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_baseline(baseline_path: Path) -> tuple[ExceptionSite, ...]:
    if not baseline_path.exists():
        raise FileNotFoundError(
            f"Baseline file does not exist: {baseline_path.as_posix()}"
        )
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    raw_sites = payload.get("sites", [])
    sites: list[ExceptionSite] = []
    for item in raw_sites:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        line = item.get("line")
        kind = item.get("kind")
        if not isinstance(path, str) or not isinstance(line, int) or not isinstance(kind, str):
            continue
        sites.append(ExceptionSite(path=path, line=line, kind=kind))
    return tuple(sorted(sites, key=lambda item: (item.path, item.line, item.kind)))


def verify_against_baseline(
    *,
    current: tuple[ExceptionSite, ...],
    baseline: tuple[ExceptionSite, ...],
) -> tuple[tuple[ExceptionSite, ...], tuple[ExceptionSite, ...], tuple[ExceptionSite, ...]]:
    current_keys = {site.key(): site for site in current}
    baseline_keys = {site.key(): site for site in baseline}

    added = tuple(
        sorted(
            (site for key, site in current_keys.items() if key not in baseline_keys),
            key=lambda item: (item.path, item.line, item.kind),
        )
    )
    removed = tuple(
        sorted(
            (site for key, site in baseline_keys.items() if key not in current_keys),
            key=lambda item: (item.path, item.line, item.kind),
        )
    )
    bare = tuple(site for site in current if site.kind == "bare_except")
    return added, removed, bare


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify catch-all exception governance against a checked-in baseline."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root path to scan; defaults to app and scripts.",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="Path to baseline JSON.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Regenerate baseline file from current repository state.",
    )
    parser.add_argument(
        "--allow-missing-root",
        action="store_true",
        help="Skip missing roots instead of failing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    roots = tuple(Path(item) for item in args.root) if args.root else DEFAULT_ROOTS
    missing = [root for root in roots if not root.exists()]
    if missing and not args.allow_missing_root:
        print("Missing scan roots: " + ", ".join(path.as_posix() for path in missing))
        return 2

    available_roots = tuple(root for root in roots if root.exists())
    current = collect_exception_sites(roots=available_roots)

    if args.write_baseline:
        write_baseline(
            baseline_path=args.baseline_path,
            roots=available_roots,
            sites=current,
        )
        print(
            f"Exception baseline refreshed: {args.baseline_path.as_posix()} "
            f"(sites={len(current)})"
        )
        return 0

    baseline = _load_baseline(args.baseline_path)
    added, removed, bare = verify_against_baseline(current=current, baseline=baseline)
    if bare:
        print("Bare except handlers are forbidden:")
        for site in bare:
            print(f"- {site.path}:{site.line} [{site.kind}]")
        return 1

    if added:
        print(
            "New catch-all handlers detected (update code or refresh baseline with approval):"
        )
        for site in added:
            print(f"- {site.path}:{site.line} [{site.kind}]")
        return 1

    if removed:
        print(f"Catch-all governance improvements detected (removed={len(removed)}).")
    print(
        "Exception governance check passed "
        f"(current={len(current)}, baseline={len(baseline)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

