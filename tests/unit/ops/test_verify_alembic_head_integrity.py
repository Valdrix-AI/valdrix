from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_alembic_head_integrity import verify_alembic_heads


def _write_migration(
    base: Path,
    filename: str,
    *,
    revision: str,
    down_revision: str | tuple[str, ...] | None,
) -> None:
    if down_revision is None:
        down_literal = "None"
    elif isinstance(down_revision, tuple):
        quoted = ", ".join(repr(item) for item in down_revision)
        down_literal = f"({quoted},)"
    else:
        down_literal = repr(down_revision)

    content = (
        f"revision = {revision!r}\n"
        f"down_revision = {down_literal}\n"
        "branch_labels = None\n"
        "depends_on = None\n"
    )
    (base / filename).write_text(content, encoding="utf-8")


def test_verify_alembic_heads_passes_with_single_head(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir(parents=True)
    _write_migration(versions, "001_initial.py", revision="001", down_revision=None)
    _write_migration(versions, "002_next.py", revision="002", down_revision="001")

    heads = verify_alembic_heads(versions)
    assert heads == ("002",)


def test_verify_alembic_heads_rejects_multiple_heads(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir(parents=True)
    _write_migration(versions, "001_initial.py", revision="001", down_revision=None)
    _write_migration(versions, "002_branch_a.py", revision="002a", down_revision="001")
    _write_migration(versions, "003_branch_b.py", revision="002b", down_revision="001")

    with pytest.raises(RuntimeError, match="single-head policy violated"):
        verify_alembic_heads(versions)


def test_verify_alembic_heads_rejects_unknown_parent_reference(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir(parents=True)
    _write_migration(versions, "001_initial.py", revision="001", down_revision=None)
    _write_migration(
        versions,
        "002_bad_parent.py",
        revision="002",
        down_revision="missing-parent",
    )

    with pytest.raises(RuntimeError, match="unknown parent revision"):
        verify_alembic_heads(versions)

