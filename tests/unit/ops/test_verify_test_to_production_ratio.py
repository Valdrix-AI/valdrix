from __future__ import annotations

from pathlib import Path

from scripts.verify_test_to_production_ratio import (
    compute_ratio_metrics,
    main,
    validate_ratio,
)


def _write_lines(path: Path, line_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"line_{idx}" for idx in range(line_count))
    path.write_text(body, encoding="utf-8")


def test_compute_ratio_metrics_counts_python_lines(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/service.py", 10)
    _write_lines(tmp_path / "scripts/check.py", 3)
    _write_lines(tmp_path / "tests/test_service.py", 5)

    metrics = compute_ratio_metrics(
        production_roots=(tmp_path / "app", tmp_path / "scripts"),
        tests_root=tmp_path / "tests",
    )
    assert metrics.production_lines == 13
    assert metrics.test_lines == 5
    assert round(metrics.ratio, 2) == 0.38


def test_validate_ratio_flags_oversized_test_surface(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/service.py", 10)
    _write_lines(tmp_path / "tests/test_service.py", 30)

    metrics, errors = validate_ratio(
        production_roots=(tmp_path / "app",),
        tests_root=tmp_path / "tests",
        max_ratio=1.30,
    )
    assert round(metrics.ratio, 2) == 3.00
    assert len(errors) == 1
    assert "exceeds budget" in errors[0]


def test_main_returns_failure_when_production_root_has_no_lines(tmp_path: Path) -> None:
    _write_lines(tmp_path / "tests/test_only.py", 5)
    assert (
        main(
            [
                "--production-root",
                str(tmp_path / "app"),
                "--production-root",
                str(tmp_path / "scripts"),
                "--tests-root",
                str(tmp_path / "tests"),
            ]
        )
        == 1
    )


def test_compute_ratio_metrics_ignores_blank_and_comment_only_lines(
    tmp_path: Path,
) -> None:
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "service.py").write_text(
        "# module comment\n\nvalue = 1\n    # indented comment\nvalue += 1\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_service.py").write_text(
        "# comment\n\nassert True\nassert True  # inline comment\n",
        encoding="utf-8",
    )

    metrics = compute_ratio_metrics(
        production_roots=(tmp_path / "app",),
        tests_root=tmp_path / "tests",
    )
    assert metrics.production_lines == 2
    assert metrics.test_lines == 2
    assert metrics.ratio == 1.0
