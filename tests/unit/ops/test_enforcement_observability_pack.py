from __future__ import annotations

from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[3]
ALERT_RULES_PATH = REPO_ROOT / "ops" / "alerts" / "enforcement_control_plane_rules.yml"
DASHBOARD_PATH = (
    REPO_ROOT / "ops" / "dashboards" / "enforcement_control_plane_overview.json"
)
EVIDENCE_DOC_PATH = REPO_ROOT / "docs" / "ops" / "alert-evidence-2026-02-25.md"


def test_enforcement_alert_rules_pack_exists_and_covers_required_signals() -> None:
    assert ALERT_RULES_PATH.exists()
    raw = ALERT_RULES_PATH.read_text(encoding="utf-8")

    required_alerts = [
        "ValdrixEnforcementErrorBudgetBurnFast",
        "ValdrixEnforcementErrorBudgetBurnSlow",
        "ValdrixEnforcementGateTimeoutSpike",
        "ValdrixEnforcementGateLockContentionSpike",
        "ValdrixEnforcementGateLatencyP95High",
        "ValdrixEnforcementGlobalThrottleHits",
        "ValdrixEnforcementApprovalQueueBacklogHigh",
        "ValdrixEnforcementExportParityMismatch",
        "ValdrixLLMFairUseDenialsSpike",
    ]
    required_metrics = [
        "valdrix_ops_enforcement_gate_failures_total",
        "valdrix_ops_enforcement_gate_lock_events_total",
        "valdrix_ops_enforcement_gate_latency_seconds_bucket",
        "valdrix_ops_enforcement_gate_decisions_total",
        "valdrix_security_rate_limit_exceeded_total",
        "valdrix_ops_enforcement_approval_queue_backlog",
        "valdrix_ops_enforcement_export_events_total",
        "valdrix_ops_llm_fair_use_denials_total",
    ]
    required_recording_rules = [
        "record: valdrix:enforcement_gate_error_ratio_5m",
        "record: valdrix:enforcement_gate_error_ratio_30m",
        "record: valdrix:enforcement_gate_error_ratio_1h",
        "record: valdrix:enforcement_gate_error_ratio_6h",
    ]

    for alert_name in required_alerts:
        assert f"alert: {alert_name}" in raw
    for metric_name in required_metrics:
        assert metric_name in raw
    for recording_rule in required_recording_rules:
        assert recording_rule in raw


def test_enforcement_dashboard_pack_is_valid_json_and_references_required_metrics() -> None:
    assert DASHBOARD_PATH.exists()
    payload = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    assert payload["title"] == "Valdrix Enforcement Control Plane"

    panels = payload.get("panels")
    assert isinstance(panels, list)
    assert len(panels) >= 6

    expressions: list[str] = []
    for panel in panels:
        targets = panel.get("targets") if isinstance(panel, dict) else None
        if not isinstance(targets, list):
            continue
        for target in targets:
            if isinstance(target, dict) and isinstance(target.get("expr"), str):
                expressions.append(target["expr"])

    required_expression_snippets = [
        "valdrix_ops_enforcement_gate_decisions_total",
        "valdrix_ops_enforcement_gate_failures_total",
        "valdrix_ops_enforcement_gate_lock_events_total",
        "valdrix_ops_enforcement_gate_latency_seconds_bucket",
        "valdrix_ops_enforcement_approval_queue_backlog",
        "valdrix_ops_enforcement_export_events_total",
        "valdrix_security_rate_limit_exceeded_total",
        "valdrix:enforcement_gate_error_ratio_5m",
        "valdrix:enforcement_gate_error_ratio_1h",
    ]
    for snippet in required_expression_snippets:
        assert any(snippet in expr for expr in expressions), snippet


def test_enforcement_observability_evidence_doc_exists() -> None:
    assert EVIDENCE_DOC_PATH.exists()
    raw = EVIDENCE_DOC_PATH.read_text(encoding="utf-8")
    assert "Enforcement Ops Evidence Pack" in raw
    assert "ValdrixEnforcementErrorBudgetBurnFast" in raw
    assert "ValdrixEnforcementErrorBudgetBurnSlow" in raw
    assert "ValdrixEnforcementGateLockContentionSpike" in raw
    assert "ValdrixEnforcementExportParityMismatch" in raw
