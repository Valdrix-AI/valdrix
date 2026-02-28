from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.run_enterprise_tdd_gate import (
    ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER,
    ANALYTICS_VISIBILITY_COVERAGE_INCLUDE,
    DEFAULT_ENFORCEMENT_STRESS_MIN_CONCURRENT_USERS,
    DEFAULT_ENFORCEMENT_STRESS_MIN_DURATION_SECONDS,
    DEFAULT_ENFORCEMENT_STRESS_REQUIRED_DATABASE_ENGINE,
    DEFAULT_KEY_ROTATION_DRILL_MAX_AGE_DAYS,
    DEFAULT_KEY_ROTATION_DRILL_PATH,
    ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS_ENV,
    ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS_ENV,
    ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS_ENV,
    ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV,
    ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE_ENV,
    ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_ENV,
    ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS_ENV,
    ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH_ENV,
    ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED_ENV,
    ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS_ENV,
    ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV,
    ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED_ENV,
    DEFAULT_ENFORCEMENT_FINANCE_GUARDRAILS_MAX_AGE_HOURS,
    DEFAULT_ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS,
    ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS_ENV,
    ENFORCEMENT_KEY_ROTATION_DRILL_PATH_ENV,
    ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS_ENV,
    ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV,
    ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED_ENV,
    ENTERPRISE_GATE_TEST_TARGETS,
    ENFORCEMENT_COVERAGE_FAIL_UNDER,
    LLM_GUARDRAIL_COVERAGE_INCLUDE,
    LLM_COVERAGE_FAIL_UNDER,
    build_gate_commands,
    compute_coverage_subset_from_xml,
    main,
    run_gate,
    verify_coverage_subset_from_xml,
)


def test_build_gate_commands_includes_required_test_targets() -> None:
    commands = build_gate_commands()
    jwt_bcp_cmd = next(
        cmd for cmd in commands if "scripts/verify_jwt_bcp_checklist.py" in cmd
    )
    ssdf_cmd = next(
        cmd for cmd in commands if "scripts/verify_ssdf_traceability_matrix.py" in cmd
    )
    sanity_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_enforcement_post_closure_sanity.py" in cmd
    )
    key_rotation_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_key_rotation_drill_evidence.py" in cmd
    )
    guard_cmd = next(
        cmd for cmd in commands if "scripts/verify_enterprise_placeholder_guards.py" in cmd
    )
    pytest_cmd = next(cmd for cmd in commands if cmd[:3] == ["uv", "run", "pytest"])

    assert jwt_bcp_cmd[:4] == ["uv", "run", "python3", "scripts/verify_jwt_bcp_checklist.py"]
    assert "--checklist-path" in jwt_bcp_cmd
    assert "docs/security/jwt_bcp_checklist_2026-02-27.json" in jwt_bcp_cmd

    assert ssdf_cmd[:4] == ["uv", "run", "python3", "scripts/verify_ssdf_traceability_matrix.py"]
    assert "--matrix-path" in ssdf_cmd
    assert "docs/security/ssdf_traceability_matrix_2026-02-25.json" in ssdf_cmd

    assert sanity_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_enforcement_post_closure_sanity.py",
    ]
    assert "--doc-path" in sanity_cmd
    assert "docs/ops/enforcement_post_closure_sanity_2026-02-26.md" in sanity_cmd
    assert "--gap-register" in sanity_cmd
    assert "docs/ops/enforcement_control_plane_gap_register_2026-02-23.md" in sanity_cmd

    assert key_rotation_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_key_rotation_drill_evidence.py",
    ]
    assert "--drill-path" in key_rotation_cmd
    assert DEFAULT_KEY_ROTATION_DRILL_PATH in key_rotation_cmd
    assert "--max-drill-age-days" in key_rotation_cmd
    assert DEFAULT_KEY_ROTATION_DRILL_MAX_AGE_DAYS in key_rotation_cmd

    assert pytest_cmd[:3] == ["uv", "run", "pytest"]
    assert "tests/unit/enforcement" in pytest_cmd
    assert "tests/unit/shared/llm/test_budget_fair_use_branches.py" in pytest_cmd
    assert "tests/unit/shared/llm/test_budget_execution_branches.py" in pytest_cmd
    assert "tests/unit/shared/llm/test_pricing_data.py" in pytest_cmd
    assert "tests/unit/core/test_budget_manager_audit.py" in pytest_cmd
    assert "tests/unit/llm/test_circuit_breaker.py" in pytest_cmd
    assert "tests/unit/llm/test_delta_analysis_exhaustive.py" in pytest_cmd
    assert "tests/unit/services/llm/test_guardrails_logic.py" in pytest_cmd
    assert "tests/unit/api/v1/test_costs_metrics_branch_paths.py" in pytest_cmd
    assert "tests/unit/api/v1/test_leadership_kpis_branch_paths.py" in pytest_cmd
    assert "tests/unit/api/v1/test_leadership_kpis_endpoints.py" in pytest_cmd
    assert "tests/unit/llm/test_usage_tracker.py" in pytest_cmd
    assert "tests/contract/test_openapi_contract.py" in pytest_cmd

    for target in ENTERPRISE_GATE_TEST_TARGETS:
        assert target in pytest_cmd

    assert guard_cmd[-2:] == ["--profile", "strict"]


def test_build_gate_commands_excludes_stress_artifact_verifier_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV, raising=False)
    monkeypatch.delenv(ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS_ENV, raising=False)
    commands = build_gate_commands()
    assert not any(
        "scripts/verify_enforcement_stress_evidence.py" in cmd for cmd in commands
    )
    assert not any(
        "scripts/verify_enforcement_failure_injection_evidence.py" in cmd
        for cmd in commands
    )
    assert not any(
        "scripts/verify_finance_guardrails_evidence.py" in cmd for cmd in commands
    )
    assert not any(
        "scripts/verify_pricing_benchmark_register.py" in cmd for cmd in commands
    )


def test_build_gate_commands_rejects_required_stress_artifact_without_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV, raising=False)
    monkeypatch.setenv(ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_ENV, "true")

    with pytest.raises(ValueError, match="ENFORCEMENT_STRESS_EVIDENCE_REQUIRED"):
        build_gate_commands()


def test_build_gate_commands_rejects_required_failure_injection_artifact_without_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH_ENV, raising=False)
    monkeypatch.setenv(ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED_ENV, "true")

    with pytest.raises(
        ValueError, match="ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED"
    ):
        build_gate_commands()


def test_build_gate_commands_rejects_required_finance_artifact_without_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV, raising=False)
    monkeypatch.setenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED_ENV, "true")

    with pytest.raises(
        ValueError, match="ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED"
    ):
        build_gate_commands()


def test_build_gate_commands_rejects_required_pricing_benchmark_register_without_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV, raising=False)
    monkeypatch.setenv(ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED_ENV, "true")

    with pytest.raises(
        ValueError, match="ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED"
    ):
        build_gate_commands()


def test_build_gate_commands_includes_stress_artifact_verifier_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV,
        "docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json",
    )
    monkeypatch.setenv(ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_ENV, "true")
    monkeypatch.setenv(ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS_ENV, "24")
    commands = build_gate_commands()

    stress_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_enforcement_stress_evidence.py" in cmd
    )
    assert stress_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_enforcement_stress_evidence.py",
    ]
    assert "--evidence-path" in stress_cmd
    assert (
        "docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json" in stress_cmd
    )
    assert "--min-duration-seconds" in stress_cmd
    assert DEFAULT_ENFORCEMENT_STRESS_MIN_DURATION_SECONDS in stress_cmd
    assert "--min-concurrent-users" in stress_cmd
    assert DEFAULT_ENFORCEMENT_STRESS_MIN_CONCURRENT_USERS in stress_cmd
    assert "--required-database-engine" in stress_cmd
    assert DEFAULT_ENFORCEMENT_STRESS_REQUIRED_DATABASE_ENGINE in stress_cmd
    assert "--max-artifact-age-hours" in stress_cmd
    assert "24" in stress_cmd


def test_build_gate_commands_includes_failure_injection_verifier_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH_ENV,
        "docs/ops/evidence/enforcement_failure_injection_2026-02-27.json",
    )
    monkeypatch.setenv(ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED_ENV, "true")
    monkeypatch.setenv(ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS_ENV, "48")

    commands = build_gate_commands()
    failure_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_enforcement_failure_injection_evidence.py" in cmd
    )
    assert failure_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_enforcement_failure_injection_evidence.py",
    ]
    assert "--evidence-path" in failure_cmd
    assert "docs/ops/evidence/enforcement_failure_injection_2026-02-27.json" in failure_cmd
    assert "--max-artifact-age-hours" in failure_cmd
    assert "48" in failure_cmd


def test_build_gate_commands_includes_finance_verifier_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV,
        "docs/ops/evidence/finance_guardrails_2026-02-27.json",
    )
    monkeypatch.setenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED_ENV, "true")
    monkeypatch.setenv(ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS_ENV, "720")

    commands = build_gate_commands()
    finance_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_finance_guardrails_evidence.py" in cmd
    )
    assert finance_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_finance_guardrails_evidence.py",
    ]
    assert "--evidence-path" in finance_cmd
    assert "docs/ops/evidence/finance_guardrails_2026-02-27.json" in finance_cmd
    assert "--max-artifact-age-hours" in finance_cmd
    assert "720" in finance_cmd


def test_build_gate_commands_uses_default_finance_max_age_when_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH_ENV,
        "docs/ops/evidence/finance_guardrails_2026-02-27.json",
    )
    monkeypatch.delenv(
        ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS_ENV,
        raising=False,
    )
    commands = build_gate_commands()
    finance_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_finance_guardrails_evidence.py" in cmd
    )
    assert "--max-artifact-age-hours" in finance_cmd
    assert DEFAULT_ENFORCEMENT_FINANCE_GUARDRAILS_MAX_AGE_HOURS in finance_cmd


def test_build_gate_commands_includes_pricing_benchmark_register_verifier_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV,
        "docs/ops/evidence/pricing_benchmark_register_2026-02-27.json",
    )
    monkeypatch.setenv(ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED_ENV, "true")
    monkeypatch.setenv(ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS_ENV, "120")

    commands = build_gate_commands()
    pricing_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_pricing_benchmark_register.py" in cmd
    )
    assert pricing_cmd[:4] == [
        "uv",
        "run",
        "python3",
        "scripts/verify_pricing_benchmark_register.py",
    ]
    assert "--register-path" in pricing_cmd
    assert "docs/ops/evidence/pricing_benchmark_register_2026-02-27.json" in pricing_cmd
    assert "--max-source-age-days" in pricing_cmd
    assert "120" in pricing_cmd


def test_build_gate_commands_uses_default_pricing_benchmark_max_age_when_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH_ENV,
        "docs/ops/evidence/pricing_benchmark_register_2026-02-27.json",
    )
    monkeypatch.delenv(
        ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS_ENV,
        raising=False,
    )
    commands = build_gate_commands()
    pricing_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_pricing_benchmark_register.py" in cmd
    )
    assert "--max-source-age-days" in pricing_cmd
    assert DEFAULT_ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS in pricing_cmd


def test_build_gate_commands_applies_stress_evidence_workload_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_STRESS_EVIDENCE_PATH_ENV,
        "docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json",
    )
    monkeypatch.setenv(ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS_ENV, "45")
    monkeypatch.setenv(ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS_ENV, "18")
    monkeypatch.setenv(
        ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE_ENV,
        "sqlite",
    )

    commands = build_gate_commands()
    stress_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_enforcement_stress_evidence.py" in cmd
    )
    assert "--min-duration-seconds" in stress_cmd
    assert "45" in stress_cmd
    assert "--min-concurrent-users" in stress_cmd
    assert "18" in stress_cmd
    assert "--required-database-engine" in stress_cmd
    assert "sqlite" in stress_cmd


def test_build_gate_commands_applies_key_rotation_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        ENFORCEMENT_KEY_ROTATION_DRILL_PATH_ENV,
        "docs/ops/key-rotation-drill-override.md",
    )
    monkeypatch.setenv(ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS_ENV, "45")
    commands = build_gate_commands()

    key_rotation_cmd = next(
        cmd
        for cmd in commands
        if "scripts/verify_key_rotation_drill_evidence.py" in cmd
    )
    assert "--drill-path" in key_rotation_cmd
    assert "docs/ops/key-rotation-drill-override.md" in key_rotation_cmd
    assert "--max-drill-age-days" in key_rotation_cmd
    assert "45" in key_rotation_cmd


def test_build_gate_commands_includes_coverage_thresholds() -> None:
    commands = build_gate_commands()

    enforcement_cmd = next(
        cmd
        for cmd in commands
        if cmd[:4] == ["uv", "run", "coverage", "report"]
        and "--include=app/modules/enforcement/*" in cmd
    )
    llm_cmd = next(
        cmd
        for cmd in commands
        if cmd[:4] == ["uv", "run", "coverage", "report"]
        and any(arg.startswith("--include=") for arg in cmd)
        and any("app/shared/llm/budget_fair_use.py" in arg for arg in cmd)
    )
    analytics_cmd = next(
        cmd
        for cmd in commands
        if cmd[:4] == ["uv", "run", "coverage", "report"]
        and any(arg.startswith("--include=") for arg in cmd)
        and any("app/shared/llm/analyzer.py" in arg for arg in cmd)
    )

    include_arg = next(arg for arg in llm_cmd if arg.startswith("--include="))
    for path in LLM_GUARDRAIL_COVERAGE_INCLUDE:
        assert path in include_arg
    assert "app/shared/llm/analyzer.py" not in include_arg
    assert "app/modules/reporting/api/v1/costs.py" not in include_arg
    analytics_include_arg = next(
        arg for arg in analytics_cmd if arg.startswith("--include=")
    )
    for path in ANALYTICS_VISIBILITY_COVERAGE_INCLUDE:
        assert path in analytics_include_arg
    assert "app/shared/llm/budget_fair_use.py" not in analytics_include_arg
    assert f"--fail-under={ENFORCEMENT_COVERAGE_FAIL_UNDER}" in enforcement_cmd
    assert f"--fail-under={LLM_COVERAGE_FAIL_UNDER}" in llm_cmd
    assert (
        f"--fail-under={ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER}" in analytics_cmd
    )


def test_main_dry_run_succeeds() -> None:
    exit_code = main(["--dry-run"])
    assert exit_code == 0


def test_compute_coverage_subset_from_xml_counts_lines_and_branches(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    enforcement_root = repo_root / "app/modules/enforcement"
    target_file = enforcement_root / "api/v1/example.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("pass\n", encoding="utf-8")

    xml_path = repo_root / "coverage-enterprise-gate.xml"
    coverage = ET.Element("coverage")
    sources = ET.SubElement(coverage, "sources")
    ET.SubElement(sources, "source").text = str(enforcement_root)
    packages = ET.SubElement(coverage, "packages")
    package = ET.SubElement(packages, "package", {"name": "api.v1"})
    classes = ET.SubElement(package, "classes")
    cls = ET.SubElement(
        classes,
        "class",
        {
            "name": "example.py",
            "filename": "api/v1/example.py",
            "line-rate": "0.66",
            "branch-rate": "0.5",
        },
    )
    lines = ET.SubElement(cls, "lines")
    ET.SubElement(lines, "line", {"number": "1", "hits": "1"})
    ET.SubElement(lines, "line", {"number": "2", "hits": "0"})
    ET.SubElement(
        lines,
        "line",
        {
            "number": "3",
            "hits": "1",
            "branch": "true",
            "condition-coverage": "50% (1/2)",
        },
    )
    ET.ElementTree(coverage).write(xml_path, encoding="utf-8", xml_declaration=True)

    totals = compute_coverage_subset_from_xml(
        xml_path=xml_path,
        include_patterns=["app/modules/enforcement/*"],
        repo_root=repo_root,
    )

    assert totals.lines_valid == 3
    assert totals.lines_covered == 2
    assert totals.branches_valid == 2
    assert totals.branches_covered == 1
    assert round(totals.percent(), 1) == 60.0


def test_run_gate_falls_back_to_xml_coverage_when_coverage_data_file_missing(monkeypatch) -> None:
    coverage_cmd = [
        "uv",
        "run",
        "coverage",
        "report",
        "--include=app/modules/enforcement/*",
        "--fail-under=95",
    ]
    monkeypatch.setattr(
        "scripts.run_enterprise_tdd_gate.build_gate_commands",
        lambda: [coverage_cmd],
    )

    def _raise_called_process_error(cmd, check, env=None):
        assert env is not None
        assert ".coverage.enterprise-gate" in env.get("COVERAGE_FILE", "")
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    fallback_calls: list[tuple[list[str], int, str]] = []

    def _record_fallback(*, xml_path, include_patterns, fail_under, label, repo_root):
        del xml_path, repo_root
        fallback_calls.append((list(include_patterns), fail_under, label))

    monkeypatch.setattr(
        "scripts.run_enterprise_tdd_gate.subprocess.run",
        _raise_called_process_error,
    )
    monkeypatch.setattr(
        "scripts.run_enterprise_tdd_gate.verify_coverage_subset_from_xml",
        _record_fallback,
    )

    assert run_gate(dry_run=False) == 0
    assert fallback_calls == [
        (
            ["app/modules/enforcement/*"],
            95,
            "app/modules/enforcement/*",
        )
    ]


def test_verify_coverage_subset_from_xml_fails_when_no_files_match(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    xml_path = repo_root / "coverage-enterprise-gate.xml"
    coverage = ET.Element("coverage")
    sources = ET.SubElement(coverage, "sources")
    ET.SubElement(sources, "source").text = str(repo_root)
    packages = ET.SubElement(coverage, "packages")
    package = ET.SubElement(packages, "package", {"name": "app"})
    classes = ET.SubElement(package, "classes")
    cls = ET.SubElement(classes, "class", {"name": "x.py", "filename": "app/x.py"})
    ET.SubElement(cls, "lines")
    ET.ElementTree(coverage).write(xml_path, encoding="utf-8", xml_declaration=True)

    with pytest.raises(RuntimeError, match="matched no measurable lines/branches"):
        verify_coverage_subset_from_xml(
            xml_path=xml_path,
            include_patterns=["app/shared/llm/analyzer.py"],
            fail_under=95,
            label="analytics",
            repo_root=repo_root,
        )


def test_run_gate_forces_debug_false_in_command_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.run_enterprise_tdd_gate.build_gate_commands",
        lambda: [["uv", "run", "python3", "-c", "print('ok')"]],
    )
    monkeypatch.setenv("DEBUG", "release")
    captured_debug_values: list[str] = []

    def _capture_run(cmd, check, env=None):
        del cmd, check
        assert env is not None
        captured_debug_values.append(str(env.get("DEBUG", "")))
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr("scripts.run_enterprise_tdd_gate.subprocess.run", _capture_run)

    assert run_gate(dry_run=False) == 0
    assert captured_debug_values == ["false"]
