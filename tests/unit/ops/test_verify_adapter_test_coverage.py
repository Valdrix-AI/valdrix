from __future__ import annotations

from pathlib import Path

from scripts.verify_adapter_test_coverage import find_uncovered_adapters, main


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_find_uncovered_adapters_detects_missing_references(tmp_path: Path) -> None:
    adapters_root = tmp_path / "adapters"
    tests_root = tmp_path / "tests"

    _write(adapters_root / "alpha.py", "VALUE = 1\n")
    _write(adapters_root / "beta.py", "VALUE = 2\n")
    _write(
        tests_root / "test_alpha_adapter.py",
        "from app.shared.adapters.alpha import VALUE\n",
    )

    missing = find_uncovered_adapters(
        adapters_root=adapters_root,
        tests_root=tests_root,
    )

    assert missing == ("beta",)


def test_find_uncovered_adapters_honors_allowlist(tmp_path: Path) -> None:
    adapters_root = tmp_path / "adapters"
    tests_root = tmp_path / "tests"
    _write(adapters_root / "beta.py", "VALUE = 2\n")

    missing = find_uncovered_adapters(
        adapters_root=adapters_root,
        tests_root=tests_root,
        allowlist={"beta"},
    )

    assert missing == ()


def test_main_returns_success_when_all_adapters_covered(tmp_path: Path) -> None:
    adapters_root = tmp_path / "adapters"
    tests_root = tmp_path / "tests"
    _write(adapters_root / "alpha.py", "VALUE = 1\n")
    _write(
        tests_root / "test_adapter_refs.py",
        "import app.shared.adapters.alpha\n",
    )

    exit_code = main(
        [
            "--adapters-root",
            str(adapters_root),
            "--tests-root",
            str(tests_root),
        ]
    )

    assert exit_code == 0

