from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_enforcement_failure_injection_evidence as generator


def test_generate_evidence_requires_separation_of_duties(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        generator.generate_evidence(
            output=tmp_path / "artifact.json",
            executed_by="same@valdrics.local",
            approved_by="same@valdrics.local",
            profile="enforcement_failure_injection",
            cwd=tmp_path,
        )


def test_generate_evidence_writes_summary_and_scenarios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}

    def _fake_run_scenario(
        scenario: generator.FailureScenario, *, cwd: Path
    ) -> tuple[dict[str, object], bool]:
        calls["count"] += 1
        passed = scenario.scenario_id != "FI-003"
        return (
            {
                "id": scenario.scenario_id,
                "status": "pass" if passed else "fail",
                "duration_seconds": 1.5,
                "checks": list(scenario.checks),
                "evidence_refs": list(scenario.selectors),
                "command": "uv run pytest --no-cov -q ...",
                "result_tail": "ok",
            },
            passed,
        )

    monkeypatch.setattr(generator, "_run_scenario", _fake_run_scenario)

    output = tmp_path / "evidence.json"
    artifact, overall_passed = generator.generate_evidence(
        output=output,
        executed_by="executor@valdrics.local",
        approved_by="approver@valdrics.local",
        profile="enforcement_failure_injection",
        cwd=tmp_path,
    )

    assert overall_passed is False
    assert calls["count"] == len(generator.SCENARIOS)
    assert artifact["summary"] == {
        "total_scenarios": len(generator.SCENARIOS),
        "passed_scenarios": len(generator.SCENARIOS) - 1,
        "failed_scenarios": 1,
        "overall_passed": False,
    }
    assert [row["id"] for row in artifact["scenarios"]] == [
        scenario.scenario_id for scenario in generator.SCENARIOS
    ]

    on_disk = json.loads(output.read_text(encoding="utf-8"))
    assert on_disk["runner"] == "staged_failure_injection"
    assert on_disk["execution_class"] == "staged"


def test_main_exit_code_follows_overall_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_generate_evidence(**_: object) -> tuple[dict[str, object], bool]:
        return (
            {
                "profile": "enforcement_failure_injection",
                "summary": {
                    "total_scenarios": 5,
                    "passed_scenarios": 5,
                    "failed_scenarios": 0,
                    "overall_passed": True,
                },
            },
            True,
        )

    monkeypatch.setattr(generator, "generate_evidence", _fake_generate_evidence)

    exit_code = generator.main(
        [
            "--output",
            str(tmp_path / "artifact.json"),
            "--executed-by",
            "exec@valdrics.local",
            "--approved-by",
            "approve@valdrics.local",
        ]
    )
    assert exit_code == 0
