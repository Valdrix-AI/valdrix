from __future__ import annotations

from scripts.run_enterprise_tdd_gate import (
    ENTERPRISE_GATE_TEST_TARGETS,
    ENFORCEMENT_COVERAGE_FAIL_UNDER,
    LLM_COVERAGE_FAIL_UNDER,
    build_gate_commands,
    main,
)


def test_build_gate_commands_includes_required_test_targets() -> None:
    commands = build_gate_commands()
    guard_cmd = commands[0]
    pytest_cmd = commands[1]

    assert pytest_cmd[:3] == ["uv", "run", "pytest"]
    assert "tests/unit/enforcement" in pytest_cmd
    assert "tests/unit/shared/llm/test_budget_fair_use_branches.py" in pytest_cmd
    assert "tests/contract/test_openapi_contract.py" in pytest_cmd

    for target in ENTERPRISE_GATE_TEST_TARGETS:
        assert target in pytest_cmd

    assert guard_cmd[-2:] == ["--profile", "strict"]


def test_build_gate_commands_includes_coverage_thresholds() -> None:
    commands = build_gate_commands()

    enforcement_cmd = commands[2]
    llm_cmd = commands[3]

    assert f"--fail-under={ENFORCEMENT_COVERAGE_FAIL_UNDER}" in enforcement_cmd
    assert f"--fail-under={LLM_COVERAGE_FAIL_UNDER}" in llm_cmd


def test_main_dry_run_succeeds() -> None:
    exit_code = main(["--dry-run"])
    assert exit_code == 0
