from __future__ import annotations

from pathlib import Path

from scripts.verify_audit_report_resolved import (
    main,
    parse_report_findings,
    validate_report_scope,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_parse_report_findings_extracts_ids(tmp_path: Path) -> None:
    report = tmp_path / "audit.md"
    _write(
        report,
        "\n".join(
            [
                "### C-01: Secret leak",
                "### H-02: Catch-all handlers",
                "### M-09: Analyzer governance",
                "### L-02: Script duplication",
            ]
        ),
    )

    assert parse_report_findings(report) == ("C-01", "H-02", "M-09", "L-02")


def test_validate_report_scope_flags_missing_findings() -> None:
    errors = validate_report_scope(
        report_findings=("C-01", "H-01"),
        expected_findings=("C-01", "H-01", "L-02"),
    )
    assert errors == ("report missing expected finding headings: L-02",)


def test_main_passes_for_c01_with_clean_template(tmp_path: Path) -> None:
    _write(
        tmp_path / ".env.example",
        "\n".join(
            [
                'APP_NAME="Valdrics"',
                "CSRF_SECRET_KEY=",
                "SMTP_USER=",
                "DB_POOL_SIZE=20",
                "DB_MAX_OVERFLOW=10",
                "DB_POOL_TIMEOUT=30",
            ]
        ),
    )

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "C-01",
        ]
    )

    assert exit_code == 0


def test_main_flags_l02_duplicate_scripts(tmp_path: Path) -> None:
    _write(tmp_path / ".env.example", "CSRF_SECRET_KEY=\nSMTP_USER=\n")
    _write(tmp_path / "scripts/check_db.py", "print('legacy')\n")
    _write(tmp_path / "scripts/db_diagnostics.py", "print('new')\n")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "L-02",
        ]
    )

    assert exit_code == 1


def test_main_flags_m09_missing_governance_tokens(tmp_path: Path) -> None:
    _write(tmp_path / ".env.example", "CSRF_SECRET_KEY=\nSMTP_USER=\n")
    _write(tmp_path / "app/shared/llm/analyzer.py", "def analyze():\n    return {}\n")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "M-09",
        ]
    )

    assert exit_code == 1
