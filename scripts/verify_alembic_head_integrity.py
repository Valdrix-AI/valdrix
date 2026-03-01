"""Verify Alembic migration graph integrity (single-head policy)."""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path


_REVISION_HEADER_RE = re.compile(r"^\s*Revision ID:\s*([a-f0-9_]+)\s*$", re.MULTILINE)
_REVISES_HEADER_RE = re.compile(r"^\s*Revises:\s*([a-f0-9_,\s]+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RevisionNode:
    revision: str
    down_revisions: tuple[str, ...]
    path: Path


def _literal_string(value: ast.expr) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value.strip()
    return None


def _parse_down_revisions(value: ast.expr) -> tuple[str, ...]:
    if isinstance(value, ast.Constant):
        if value.value is None:
            return tuple()
        if isinstance(value.value, str):
            normalized = value.value.strip()
            return (normalized,) if normalized else tuple()
        return tuple()
    if isinstance(value, (ast.Tuple, ast.List)):
        refs: list[str] = []
        for item in value.elts:
            normalized = _literal_string(item)
            if normalized:
                refs.append(normalized)
        return tuple(refs)
    return tuple()


def _parse_revision_file(path: Path) -> RevisionNode:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    revision: str | None = None
    down_revisions: tuple[str, ...] = tuple()

    for node in module.body:
        target_name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
                    value = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value

        if not target_name or value is None:
            continue
        if target_name == "revision":
            revision = _literal_string(value) or revision
        elif target_name == "down_revision":
            down_revisions = _parse_down_revisions(value)

    if not revision:
        header_match = _REVISION_HEADER_RE.search(source)
        if header_match:
            revision = header_match.group(1).strip()
    if not down_revisions:
        revises_match = _REVISES_HEADER_RE.search(source)
        if revises_match:
            tokens = [
                token.strip()
                for token in revises_match.group(1).split(",")
                if token.strip()
            ]
            down_revisions = tuple(tokens)

    if not revision:
        raise RuntimeError(f"Migration file is missing revision identifier: {path}")
    return RevisionNode(revision=revision, down_revisions=down_revisions, path=path)


def verify_alembic_heads(migrations_path: Path) -> tuple[str, ...]:
    if not migrations_path.exists():
        raise RuntimeError(f"Migrations path not found: {migrations_path}")

    revision_files = sorted(
        p for p in migrations_path.glob("*.py") if p.name != "__init__.py"
    )
    if not revision_files:
        raise RuntimeError(f"No migration files found under: {migrations_path}")

    nodes = [_parse_revision_file(path) for path in revision_files]
    revisions = {node.revision for node in nodes}

    if len(revisions) != len(nodes):
        raise RuntimeError("Duplicate Alembic revision identifiers detected.")

    referenced: set[str] = set()
    for node in nodes:
        for parent in node.down_revisions:
            if parent not in revisions:
                raise RuntimeError(
                    "Alembic migration graph references unknown parent revision "
                    f"{parent!r} from {node.path}"
                )
            referenced.add(parent)

    heads = tuple(sorted(revision for revision in revisions if revision not in referenced))
    if len(heads) != 1:
        raise RuntimeError(
            "Alembic single-head policy violated: "
            f"expected exactly 1 head, found {len(heads)} ({', '.join(heads)})."
        )
    return heads


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Alembic migration graph has exactly one head."
    )
    parser.add_argument(
        "--migrations-path",
        default="migrations/versions",
        help="Path to Alembic revisions directory.",
    )
    args = parser.parse_args()

    heads = verify_alembic_heads(Path(args.migrations_path))
    print(
        "Alembic migration head integrity check passed. "
        f"Head revision: {heads[0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
