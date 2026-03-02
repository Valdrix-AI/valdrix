from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_pkg_fin_policy_decisions import (
    REQUIRED_DECISION_BACKLOG_IDS,
    main,
    verify_evidence,
)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_decision_item(
    item_id: str,
    *,
    resolution: str = "locked_prelaunch",
    launch_blocking: bool = False,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": item_id,
        "owner_function": "finance" if item_id.startswith("FIN-") else "product",
        "owner": (
            "finance-owner@valdrics.io"
            if item_id.startswith("FIN-")
            else "product-owner@valdrics.io"
        ),
        "decision_summary": f"{item_id} policy resolution recorded for release evidence.",
        "resolution": resolution,
        "launch_blocking": launch_blocking,
        "approval_record_ref": f"{item_id}-APPROVAL-2026-02-28",
        "approved_at": "2026-02-28T05:45:00Z",
    }
    if resolution == "scheduled_postlaunch":
        item["target_date"] = "2026-03-31"
        item["success_criteria"] = (
            "Finance and product sign-off captured in the next monthly committee packet."
        )
    return item


def _build_decision_backlog() -> dict[str, object]:
    required_ids = list(REQUIRED_DECISION_BACKLOG_IDS)
    launch_blockers = {
        "PKG-004",
        "PKG-005",
        "PKG-009",
        "PKG-011",
        "PKG-012",
        "FIN-001",
        "FIN-002",
        "FIN-003",
    }
    decision_items: list[dict[str, object]] = []
    for item_id in required_ids:
        if item_id in {"PKG-029", "PKG-030", "PKG-031"}:
            decision_items.append(
                _build_decision_item(
                    item_id,
                    resolution="scheduled_postlaunch",
                    launch_blocking=False,
                )
            )
            continue
        decision_items.append(
            _build_decision_item(item_id, launch_blocking=item_id in launch_blockers)
        )
    return {
        "required_decision_ids": required_ids,
        "decision_items": decision_items,
    }


def _valid_payload() -> dict[str, object]:
    return {
        "captured_at": "2026-02-28T06:30:00Z",
        "window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-02-28T23:59:59Z",
            "label": "2026-01_to_2026-02",
        },
        "telemetry": {
            "months_observed": 2,
            "source_type": "synthetic_prelaunch",
            "tier_unit_economics": [
                {
                    "tier": "starter",
                    "mrr_usd": 62000.0,
                    "effective_mrr_usd": 56800.0,
                    "llm_cogs_usd": 2100.0,
                    "infra_cogs_usd": 5100.0,
                    "support_cogs_usd": 1600.0,
                },
                {
                    "tier": "growth",
                    "mrr_usd": 126000.0,
                    "effective_mrr_usd": 115000.0,
                    "llm_cogs_usd": 4200.0,
                    "infra_cogs_usd": 9300.0,
                    "support_cogs_usd": 2700.0,
                },
                {
                    "tier": "pro",
                    "mrr_usd": 188000.0,
                    "effective_mrr_usd": 171000.0,
                    "llm_cogs_usd": 7300.0,
                    "infra_cogs_usd": 15300.0,
                    "support_cogs_usd": 4200.0,
                },
                {
                    "tier": "enterprise",
                    "mrr_usd": 255000.0,
                    "effective_mrr_usd": 239000.0,
                    "llm_cogs_usd": 10100.0,
                    "infra_cogs_usd": 20300.0,
                    "support_cogs_usd": 7300.0,
                },
            ],
        },
        "policy_decisions": {
            "enterprise_pricing_model": "hybrid",
            "enterprise_floor_usd_monthly": 799.0,
            "max_annual_discount_percent": 20.0,
            "pricing_motion_allowed": False,
            "growth_auto_remediation_scope": "nonprod_only",
            "pro_enforcement_boundary": "required_for_prod_enforcement",
            "migration_strategy": "grandfather_timeboxed",
            "migration_window_days": 90,
        },
        "approvals": {
            "finance_owner": "finance-owner@valdrics.io",
            "product_owner": "product-owner@valdrics.io",
            "go_to_market_owner": "gtm-owner@valdrics.io",
            "governance_mode": "founder_acting_roles_prelaunch",
            "approval_record_ref": "PKG-FIN-APPROVAL-2026-02-28",
            "approved_at": "2026-02-28T05:45:00Z",
        },
        "decision_backlog": _build_decision_backlog(),
        "gate_results": {
            "pkg_fin_gate_policy_decisions_complete": True,
            "pkg_fin_gate_telemetry_window_sufficient": True,
            "pkg_fin_gate_approvals_complete": True,
            "pkg_fin_gate_pricing_motion_guarded": True,
            "pkg_fin_gate_backlog_coverage_complete": True,
            "pkg_fin_gate_launch_blockers_resolved": True,
            "pkg_fin_gate_postlaunch_commitments_scheduled": True,
        },
    }


def test_verify_pkg_fin_policy_decisions_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, _valid_payload())
    assert verify_evidence(evidence_path=path) == 0


def test_verify_pkg_fin_policy_decisions_rejects_gate_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["gate_results"]["pkg_fin_gate_policy_decisions_complete"] = False
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(
        ValueError, match="gate_results.pkg_fin_gate_policy_decisions_complete mismatch"
    ):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_short_telemetry_window(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["telemetry"]["months_observed"] = 1
    payload["gate_results"]["pkg_fin_gate_telemetry_window_sufficient"] = False
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(
        ValueError,
        match="PKG/FIN policy decision verification failed",
    ):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_missing_required_tier(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["telemetry"]["tier_unit_economics"] = payload["telemetry"][
        "tier_unit_economics"
    ][:3]
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required tiers"):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_invalid_policy_choice(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["policy_decisions"]["enterprise_pricing_model"] = "unknown"
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(
        ValueError, match="policy_decisions.enterprise_pricing_model must be one of"
    ):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_pricing_motion_true_with_synthetic_telemetry(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["policy_decisions"]["pricing_motion_allowed"] = True
    payload["gate_results"]["pkg_fin_gate_pricing_motion_guarded"] = False
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(
        ValueError,
        match="PKG/FIN policy decision verification failed",
    ):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_requires_distinct_owners_in_segregated_mode(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["approvals"]["governance_mode"] = "segregated_owners"
    payload["approvals"]["go_to_market_owner"] = payload["approvals"]["finance_owner"]
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(
        ValueError,
        match="requires distinct finance/product/go-to-market owners",
    ):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_too_old_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pkg-fin-policy.json"
    payload = _valid_payload()
    payload["captured_at"] = "2025-01-01T00:00:00Z"
    _write(path, payload)
    with pytest.raises(ValueError, match="too old"):
        verify_evidence(evidence_path=path, max_artifact_age_hours=0.01)


def test_verify_pkg_fin_policy_decisions_rejects_placeholder_values(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["approvals"]["finance_owner"] = "finance.owner@example.com"
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="must not contain placeholder tokens"):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_missing_decision_item(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["decision_backlog"]["decision_items"] = payload["decision_backlog"][
        "decision_items"
    ][:-1]
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required decisions"):
        verify_evidence(evidence_path=path)


def test_verify_pkg_fin_policy_decisions_rejects_launch_blocker_not_locked_prelaunch(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    decision_items = payload["decision_backlog"]["decision_items"]
    for item in decision_items:
        if item["id"] == "PKG-004":
            item["resolution"] = "scheduled_postlaunch"
            item["launch_blocking"] = True
            item["target_date"] = "2026-03-31"
            item["success_criteria"] = "Launch blocker should have been resolved prelaunch."
            break
    payload["gate_results"]["pkg_fin_gate_launch_blockers_resolved"] = False
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="PKG/FIN policy decision verification failed"):
        verify_evidence(evidence_path=path)


def test_main_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "pkg-fin-policy.json"
    _write(path, _valid_payload())
    assert main(["--evidence-path", str(path)]) == 0
