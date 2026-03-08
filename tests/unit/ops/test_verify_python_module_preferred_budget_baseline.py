from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_python_module_preferred_budget_baseline import (
    main,
    verify_against_baseline,
)
from scripts.verify_python_module_size_budget import ModuleSizePreferredBreach


def _write_lines(path: Path, line_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line_{idx}" for idx in range(line_count)), encoding="utf-8")


def test_verify_against_baseline_reports_added_removed_and_changed() -> None:
    baseline = (
        ModuleSizePreferredBreach("app/a.py", 501, 500),
        ModuleSizePreferredBreach("app/b.py", 520, 500),
    )
    current = (
        ModuleSizePreferredBreach("app/b.py", 521, 500),
        ModuleSizePreferredBreach("app/c.py", 530, 500),
    )

    added, removed, changed = verify_against_baseline(
        current=current,
        baseline=baseline,
    )

    assert [item.path for item in added] == ["app/c.py"]
    assert [item.path for item in removed] == ["app/a.py"]
    assert [(old.path, old.lines, new.lines) for old, new in changed] == [
        ("app/b.py", 520, 521)
    ]


def test_main_roundtrip_write_and_verify(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/ok.py", 100)
    _write_lines(tmp_path / "app/large.py", 501)
    baseline_path = tmp_path / "baseline.json"

    write_exit = main(
        [
            "--root",
            str(tmp_path),
            "--baseline-path",
            str(baseline_path),
            "--write-baseline",
        ]
    )
    assert write_exit == 0

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert payload["breaches"][0]["path"] == "app/large.py"

    verify_exit = main(
        [
            "--root",
            str(tmp_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )
    assert verify_exit == 0


def test_main_fails_when_repo_drift_exceeds_baseline(tmp_path: Path) -> None:
    _write_lines(tmp_path / "app/large.py", 505)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "root": str(tmp_path),
                "breaches": [
                    {
                        "path": "app/large.py",
                        "lines": 501,
                        "preferred_max_lines": 500,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )
    assert exit_code == 1
