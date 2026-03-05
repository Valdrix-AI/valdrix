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


def _write_lines(path: Path, count: int) -> None:
    body = "\n".join(f"line_{idx}" for idx in range(count))
    _write(path, body)


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


def test_main_passes_m01_with_compact_optimization_structure(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/verify_python_module_size_budget.py",
        "DEFAULT_MAX_LINES = 600\n",
    )
    _write(tmp_path / "app/modules/optimization/domain/service.py", "pass\n")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "M-01",
        ]
    )
    assert exit_code == 0


def test_main_flags_m01_when_file_budget_exceeded(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/verify_python_module_size_budget.py",
        "DEFAULT_MAX_LINES = 600\n",
    )
    for idx in range(106):
        _write(
            tmp_path / f"app/modules/optimization/domain/generated_{idx}.py",
            "pass\n",
        )

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "M-01",
        ]
    )
    assert exit_code == 1


def test_main_flags_m03_when_bundle_exceeds_default_budget(tmp_path: Path) -> None:
    _write_lines(
        tmp_path / "app/modules/governance/domain/security/compliance_pack_bundle.py",
        601,
    )

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "M-03",
        ]
    )
    assert exit_code == 1


def test_main_passes_h07_with_ratio_governance_and_improved_ratio(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/run_enterprise_tdd_gate.py",
        "\n".join(
            [
                "--cov-report=xml:coverage-enterprise-gate.xml",
                "verify_coverage_subset_from_xml",
                "scripts/verify_test_to_production_ratio.py",
            ]
        ),
    )
    _write(tmp_path / "scripts/verify_test_to_production_ratio.py", "pass\n")
    _write_lines(tmp_path / "app/service.py", 100)
    _write_lines(tmp_path / "tests/test_service.py", 120)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "H-07",
        ]
    )

    assert exit_code == 0


def test_main_flags_h07_when_ratio_exceeds_budget(tmp_path: Path) -> None:
    _write(
        tmp_path / "scripts/run_enterprise_tdd_gate.py",
        "\n".join(
            [
                "--cov-report=xml:coverage-enterprise-gate.xml",
                "verify_coverage_subset_from_xml",
                "scripts/verify_test_to_production_ratio.py",
            ]
        ),
    )
    _write(tmp_path / "scripts/verify_test_to_production_ratio.py", "pass\n")
    _write_lines(tmp_path / "app/service.py", 50)
    _write_lines(tmp_path / "tests/test_service.py", 100)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-report-check",
            "--finding",
            "H-07",
        ]
    )

    assert exit_code == 1
