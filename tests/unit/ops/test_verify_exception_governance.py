from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_exception_governance import (
    ExceptionSite,
    collect_exception_sites,
    main,
    verify_against_baseline,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_exception_sites_detects_catch_all_variants(tmp_path: Path) -> None:
    root = tmp_path / "code"
    _write(
        root / "a.py",
        "\n".join(
            [
                "try:",
                "    raise RuntimeError('x')",
                "except Exception:",
                "    pass",
                "try:",
                "    raise RuntimeError('y')",
                "except (ValueError, Exception):",
                "    pass",
                "try:",
                "    raise RuntimeError('z')",
                "except:",
                "    pass",
            ]
        ),
    )

    sites = collect_exception_sites(roots=(root,))
    assert [site.kind for site in sites] == [
        "exception",
        "tuple_exception",
        "bare_except",
    ]


def test_verify_against_baseline_reports_added_and_bare() -> None:
    baseline = (ExceptionSite(path="app/x.py", line=10, kind="exception"),)
    current = baseline + (
        ExceptionSite(path="app/y.py", line=20, kind="tuple_exception"),
        ExceptionSite(path="app/z.py", line=30, kind="bare_except"),
    )
    added, removed, bare = verify_against_baseline(current=current, baseline=baseline)

    assert [site.key() for site in added] == [
        "app/y.py:20:tuple_exception",
        "app/z.py:30:bare_except",
    ]
    assert removed == ()
    assert [site.key() for site in bare] == ["app/z.py:30:bare_except"]


def test_main_write_baseline_and_verify_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "code"
    baseline_path = tmp_path / "baseline.json"
    _write(
        root / "sample.py",
        "\n".join(
            [
                "def f():",
                "    try:",
                "        return 1",
                "    except Exception as exc:",
                "        return str(exc)",
            ]
        ),
    )

    write_exit = main(
        [
            "--root",
            str(root),
            "--baseline-path",
            str(baseline_path),
            "--write-baseline",
        ]
    )
    assert write_exit == 0
    raw = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert raw["sites"][0]["kind"] == "exception"

    verify_exit = main(
        [
            "--root",
            str(root),
            "--baseline-path",
            str(baseline_path),
        ]
    )
    assert verify_exit == 0


def test_repo_baseline_matches_current_exception_sites() -> None:
    exit_code = main(
        [
            "--root",
            str(REPO_ROOT / "app"),
            "--root",
            str(REPO_ROOT / "scripts"),
            "--baseline-path",
            str(REPO_ROOT / "docs/ops/evidence/exception_governance_baseline.json"),
        ]
    )
    assert exit_code == 0
