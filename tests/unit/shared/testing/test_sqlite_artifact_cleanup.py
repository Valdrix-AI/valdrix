from __future__ import annotations

from pathlib import Path

from app.shared.testing.sqlite_artifact_cleanup import cleanup_sqlite_test_artifacts


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_cleanup_sqlite_test_artifacts_deletes_known_patterns(tmp_path: Path) -> None:
    target_files = [
        tmp_path / "test_a.sqlite",
        tmp_path / "test_a.sqlite-journal",
        tmp_path / "test_b.sqlite-wal",
        tmp_path / "tmp_test_x.sqlite",
        tmp_path / "tmp_aiosqlite_y.sqlite-shm",
        tmp_path / "tmp_sqlite3_z.sqlite",
    ]
    for path in target_files:
        _touch(path)

    deleted = cleanup_sqlite_test_artifacts(tmp_path)

    deleted_names = {path.name for path in deleted}
    assert deleted_names == {path.name for path in target_files}
    assert all(not path.exists() for path in target_files)


def test_cleanup_sqlite_test_artifacts_preserves_non_matching_files(
    tmp_path: Path,
) -> None:
    keep_files = [
        tmp_path / "notes.txt",
        tmp_path / "sqlite_report.md",
        tmp_path / "test_data.sqlite.bak",
        tmp_path / "tmp_sqlite3_report.json",
    ]
    for path in keep_files:
        _touch(path)

    deleted = cleanup_sqlite_test_artifacts(tmp_path)

    assert deleted == ()
    assert all(path.exists() for path in keep_files)

