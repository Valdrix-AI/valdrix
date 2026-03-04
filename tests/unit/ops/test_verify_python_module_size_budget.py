from __future__ import annotations

from pathlib import Path

from scripts.verify_python_module_size_budget import (
    collect_module_size_violations,
    main,
)


def _write_lines(path: Path, line_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"line_{idx}" for idx in range(line_count))
    path.write_text(body, encoding="utf-8")


def test_collect_module_size_violations_uses_default_budget(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/small.py", 10)
    _write_lines(tmp_path / "app/large.py", 1200)

    violations = collect_module_size_violations(tmp_path, default_max_lines=1000)
    assert [item.path for item in violations] == ["app/large.py"]


def test_collect_module_size_violations_honors_overrides(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/big.py", 1200)

    violations = collect_module_size_violations(
        tmp_path,
        default_max_lines=1000,
        overrides={"app/big.py": 1300},
    )
    assert violations == ()


def test_main_returns_failure_when_any_module_exceeds_budget(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/too_big.py", 1100)
    assert main(["--root", str(tmp_path), "--default-max-lines", "1000"]) == 1
