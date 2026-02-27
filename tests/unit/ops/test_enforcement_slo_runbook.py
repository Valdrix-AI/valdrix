from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "enforcement_incident_response.md"


def test_enforcement_runbook_includes_burn_rate_release_policy() -> None:
    assert RUNBOOK_PATH.exists()
    raw = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "SLO Burn-Rate Policy (BSAFE-016)" in raw
    assert "99.9%" in raw
    assert "ValdrixEnforcementErrorBudgetBurnFast" in raw
    assert "ValdrixEnforcementErrorBudgetBurnSlow" in raw
    assert "14.4x" in raw
    assert "6x" in raw
    assert "Any firing burn-rate alert blocks release promotion." in raw
