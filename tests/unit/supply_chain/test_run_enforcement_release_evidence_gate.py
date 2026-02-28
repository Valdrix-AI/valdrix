from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.run_enforcement_release_evidence_gate import (
    build_gate_environment,
    main,
    run_release_gate,
)


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_build_gate_environment_sets_required_env_vars(tmp_path: Path) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    _write(stress)
    _write(failure)

    env = build_gate_environment(
        stress_evidence_path=stress,
        failure_evidence_path=failure,
        finance_evidence_path=None,
        finance_evidence_required=False,
        pricing_benchmark_register_path=None,
        pricing_benchmark_register_required=False,
        pkg_fin_policy_decisions_path=None,
        pkg_fin_policy_decisions_required=False,
        stress_max_age_hours=24.0,
        failure_max_age_hours=36.0,
        finance_max_age_hours=744.0,
        pricing_benchmark_max_source_age_days=120.0,
        pkg_fin_policy_decisions_max_age_hours=744.0,
        stress_min_duration_seconds=45,
        stress_min_concurrent_users=12,
        stress_required_database_engine="postgresql",
    )

    assert env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED"] == "true"
    assert env["ENFORCEMENT_STRESS_EVIDENCE_PATH"] == str(stress.resolve())
    assert env["ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS"] == "24.0"
    assert env["ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS"] == "45"
    assert env["ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS"] == "12"
    assert env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE"] == "postgresql"

    assert env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED"] == "true"
    assert env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH"] == str(
        failure.resolve()
    )
    assert env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS"] == "36.0"
    assert "ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH" not in env
    assert "ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_PATH" not in env
    assert "ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH" not in env


def test_build_gate_environment_rejects_missing_artifacts(tmp_path: Path) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    _write(stress)

    with pytest.raises(FileNotFoundError, match="failure_evidence_path"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )


def test_build_gate_environment_rejects_non_positive_values(tmp_path: Path) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    _write(stress)
    _write(failure)

    with pytest.raises(ValueError, match="stress_max_age_hours"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=0.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="stress_min_duration_seconds"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=0,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="stress_required_database_engine"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="",
        )

    with pytest.raises(ValueError, match="finance_max_age_hours"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=0.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="finance_evidence_required is true"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=True,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="pricing_benchmark_register_required is true"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=True,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="pkg_fin_policy_decisions_required is true"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=True,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="pricing_benchmark_max_source_age_days"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=0.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )

    with pytest.raises(ValueError, match="pkg_fin_policy_decisions_max_age_hours"):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=24.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=0.0,
            stress_min_duration_seconds=30,
            stress_min_concurrent_users=10,
            stress_required_database_engine="postgresql",
        )


def test_run_release_gate_invokes_enterprise_gate_with_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    finance = tmp_path / "finance.json"
    pricing = tmp_path / "pricing.json"
    pkg_fin_policy = tmp_path / "pkg-fin-policy.json"
    _write(stress)
    _write(failure)
    _write(finance)
    _write(pricing)
    _write(pkg_fin_policy)

    captured: dict[str, object] = {}

    def _fake_run(cmd, *, check: bool, env: dict[str, str]):
        del check
        captured["cmd"] = list(cmd)
        captured["env"] = dict(env)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(
        "scripts.run_enforcement_release_evidence_gate.subprocess.run",
        _fake_run,
    )

    exit_code = run_release_gate(
        stress_evidence_path=stress,
        failure_evidence_path=failure,
        finance_evidence_path=finance,
        finance_evidence_required=True,
        pricing_benchmark_register_path=pricing,
        pricing_benchmark_register_required=True,
        pkg_fin_policy_decisions_path=pkg_fin_policy,
        pkg_fin_policy_decisions_required=True,
        stress_max_age_hours=24.0,
        failure_max_age_hours=24.0,
        finance_max_age_hours=720.0,
        pricing_benchmark_max_source_age_days=90.0,
        pkg_fin_policy_decisions_max_age_hours=720.0,
        stress_min_duration_seconds=30,
        stress_min_concurrent_users=10,
        stress_required_database_engine="postgresql",
        dry_run=True,
    )
    assert exit_code == 0
    assert captured["cmd"] == [
        "uv",
        "run",
        "python3",
        "scripts/run_enterprise_tdd_gate.py",
        "--dry-run",
    ]
    env = captured["env"]
    assert env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED"] == "true"
    assert env["ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED"] == "true"
    assert env["ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE"] == "postgresql"
    assert env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED"] == "true"
    assert env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH"] == str(finance.resolve())
    assert env["ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS"] == "720.0"
    assert env["ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED"] == "true"
    assert env["ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH"] == str(pricing.resolve())
    assert env["ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS"] == "90.0"
    assert env["ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_REQUIRED"] == "true"
    assert env["ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_PATH"] == str(
        pkg_fin_policy.resolve()
    )
    assert env["ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_MAX_AGE_HOURS"] == "720.0"


def test_build_gate_environment_rejects_required_finance_telemetry_without_path(
    tmp_path: Path,
) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    _write(stress)
    _write(failure)

    with pytest.raises(
        ValueError, match="finance_telemetry_snapshot_required is true"
    ):
        build_gate_environment(
            stress_evidence_path=stress,
            failure_evidence_path=failure,
            finance_evidence_path=None,
            finance_evidence_required=False,
            pricing_benchmark_register_path=None,
            pricing_benchmark_register_required=False,
            pkg_fin_policy_decisions_path=None,
            pkg_fin_policy_decisions_required=False,
            stress_max_age_hours=24.0,
            failure_max_age_hours=36.0,
            finance_max_age_hours=744.0,
            pricing_benchmark_max_source_age_days=120.0,
            pkg_fin_policy_decisions_max_age_hours=744.0,
            stress_min_duration_seconds=45,
            stress_min_concurrent_users=12,
            stress_required_database_engine="postgresql",
            finance_telemetry_snapshot_path=None,
            finance_telemetry_snapshot_required=True,
            finance_telemetry_snapshot_max_age_hours=744.0,
        )


def test_build_gate_environment_sets_finance_telemetry_env_when_provided(
    tmp_path: Path,
) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    telemetry = tmp_path / "telemetry.json"
    _write(stress)
    _write(failure)
    _write(telemetry)

    env = build_gate_environment(
        stress_evidence_path=stress,
        failure_evidence_path=failure,
        finance_evidence_path=None,
        finance_evidence_required=False,
        pricing_benchmark_register_path=None,
        pricing_benchmark_register_required=False,
        pkg_fin_policy_decisions_path=None,
        pkg_fin_policy_decisions_required=False,
        stress_max_age_hours=24.0,
        failure_max_age_hours=36.0,
        finance_max_age_hours=744.0,
        pricing_benchmark_max_source_age_days=120.0,
        pkg_fin_policy_decisions_max_age_hours=744.0,
        stress_min_duration_seconds=45,
        stress_min_concurrent_users=12,
        stress_required_database_engine="postgresql",
        finance_telemetry_snapshot_path=telemetry,
        finance_telemetry_snapshot_required=True,
        finance_telemetry_snapshot_max_age_hours=720.0,
    )

    assert env["ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_REQUIRED"] == "true"
    assert env["ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_PATH"] == str(telemetry.resolve())
    assert env["ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_MAX_AGE_HOURS"] == "720.0"


def test_main_dry_run_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stress = tmp_path / "stress.json"
    failure = tmp_path / "failure.json"
    _write(stress)
    _write(failure)

    monkeypatch.setattr(
        "scripts.run_enforcement_release_evidence_gate.subprocess.run",
        lambda cmd, *, check, env: subprocess.CompletedProcess(args=cmd, returncode=0),
    )

    exit_code = main(
        [
            "--stress-evidence-path",
            str(stress),
            "--failure-evidence-path",
            str(failure),
            "--finance-evidence-path",
            str(failure),
            "--finance-evidence-required",
            "--pricing-benchmark-register-path",
            str(failure),
            "--pricing-benchmark-register-required",
            "--pkg-fin-policy-decisions-path",
            str(failure),
            "--pkg-fin-policy-decisions-required",
            "--dry-run",
        ]
    )
    assert exit_code == 0
