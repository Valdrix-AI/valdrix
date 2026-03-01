from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_pkg_fin_operational_readiness import (
    main,
    verify_operational_readiness,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = (
    REPO_ROOT / "docs" / "ops" / "evidence" / "pkg_fin_policy_decisions_2026-02-28.json"
)
FINANCE_PATH = (
    REPO_ROOT / "docs" / "ops" / "evidence" / "finance_guardrails_2026-02-27.json"
)
TELEMETRY_PATH = (
    REPO_ROOT / "docs" / "ops" / "evidence" / "finance_telemetry_snapshot_2026-02-28.json"
)


def test_verify_operational_readiness_returns_expected_prelaunch_summary() -> None:
    summary = verify_operational_readiness(
        policy_decisions_path=POLICY_PATH,
        finance_guardrails_path=FINANCE_PATH,
        telemetry_snapshot_path=TELEMETRY_PATH,
    )

    derived = summary["derived"]
    assert derived["policy_all_gates_pass"] is True
    assert derived["finance_all_gates_pass"] is True
    assert derived["telemetry_all_gates_pass"] is True
    assert derived["prelaunch_operational_ready"] is True
    assert derived["postlaunch_pricing_motion_ready"] is False
    assert derived["production_observed_telemetry_ready"] is False
    assert derived["segregated_approval_governance_ready"] is False

    remaining = summary["remaining_work_items"]
    assert len(remaining) == 2
    assert any("production_observed telemetry" in item for item in remaining)
    assert any("segregated_owners" in item for item in remaining)


def test_verify_operational_readiness_can_fail_on_required_production_telemetry() -> None:
    with pytest.raises(ValueError, match="production_observed telemetry requirement failed"):
        verify_operational_readiness(
            policy_decisions_path=POLICY_PATH,
            finance_guardrails_path=FINANCE_PATH,
            telemetry_snapshot_path=TELEMETRY_PATH,
            require_production_observed_telemetry=True,
        )


def test_verify_operational_readiness_can_fail_on_required_segregated_owners() -> None:
    with pytest.raises(ValueError, match="segregated owner governance requirement failed"):
        verify_operational_readiness(
            policy_decisions_path=POLICY_PATH,
            finance_guardrails_path=FINANCE_PATH,
            telemetry_snapshot_path=TELEMETRY_PATH,
            require_segregated_owners=True,
        )


def test_main_writes_summary_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "pkg_fin_operational_readiness.json"

    assert (
        main(
            [
                "--policy-decisions-path",
                str(POLICY_PATH),
                "--finance-guardrails-path",
                str(FINANCE_PATH),
                "--telemetry-snapshot-path",
                str(TELEMETRY_PATH),
                "--output-path",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["derived"]["prelaunch_operational_ready"] is True
    assert payload["derived"]["postlaunch_pricing_motion_ready"] is False
