from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_landing_component_budget import (
    LandingBudgetVerificationError,
    verify_landing_component_budget,
)


def test_verify_landing_component_budget_accepts_repo_state() -> None:
    summary = verify_landing_component_budget()
    assert summary["hero_lines"] <= summary["max_hero_lines"]
    assert summary["required_component_count"] >= 10


def test_verify_landing_component_budget_rejects_excessive_hero_lines(
    tmp_path: Path,
) -> None:
    hero_path = tmp_path / "LandingHero.svelte"
    hero_path.write_text("\n".join(["line"] * 220), encoding="utf-8")

    component_dir = tmp_path / "landing"
    component_dir.mkdir(parents=True)
    for name in (
        "LandingHeroCopy.svelte",
        "LandingSignalMapCard.svelte",
        "LandingRoiSimulator.svelte",
        "LandingCloudHookSection.svelte",
        "LandingWorkflowSection.svelte",
        "LandingBenefitsSection.svelte",
        "LandingPlansSection.svelte",
        "LandingPersonaSection.svelte",
        "LandingCapabilitiesSection.svelte",
        "LandingTrustSection.svelte",
        "LandingRoiPlannerCta.svelte",
    ):
        (component_dir / name).write_text("<div />\n", encoding="utf-8")

    with pytest.raises(LandingBudgetVerificationError, match="line budget exceeded"):
        verify_landing_component_budget(
            hero_path=hero_path,
            component_dir=component_dir,
            max_hero_lines=200,
        )


def test_verify_landing_component_budget_rejects_missing_components(
    tmp_path: Path,
) -> None:
    hero_path = tmp_path / "LandingHero.svelte"
    hero_path.write_text("line\n", encoding="utf-8")

    component_dir = tmp_path / "landing"
    component_dir.mkdir(parents=True)

    with pytest.raises(LandingBudgetVerificationError, match="components missing"):
        verify_landing_component_budget(
            hero_path=hero_path,
            component_dir=component_dir,
            max_hero_lines=200,
        )
