from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_prometheus_alerts_reference_current_exported_metrics() -> None:
    alerts = yaml.safe_load(
        (REPO_ROOT / "prometheus/alerts.yml").read_text(encoding="utf-8")
    )
    assert isinstance(alerts, dict)

    expressions = []
    for group in alerts["groups"]:
        for rule in group["rules"]:
            expressions.append(str(rule["expr"]))

    combined = "\n".join(expressions)
    assert "valdrics_ops_llm_spend_usd_total" in combined
    assert "valdrics_ops_zombies_detected_total" in combined
    assert "valdrics_ops_scan_failure_total" in combined
    assert "valdrics_ops_runtime_carbon_emissions_kg_total" in combined
    assert "http_request_duration_highr_seconds_bucket" in combined
    assert "valdrics_llm_cost_usd" not in combined
    assert "valdrics_scan_errors_total" not in combined
    assert "valdrics_carbon_emissions_kg" not in combined
    assert "http_request_duration_seconds_bucket" not in combined


def test_finops_dashboard_references_current_metrics() -> None:
    dashboard = json.loads(
        (REPO_ROOT / "grafana/dashboards/finops-overview.json").read_text(
            encoding="utf-8"
        )
    )

    queries = []
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            queries.append(str(target.get("expr", "")))

    combined = "\n".join(queries)
    assert "valdrics_ops_potential_savings_monthly" in combined
    assert "valdrics_ops_zombies_detected_total" in combined
    assert "valdrics_ops_runtime_carbon_emissions_kg_total" in combined
    assert "valdrics_ops_scan_success_total" in combined
    assert "valdrics_ops_llm_spend_usd_total" in combined
    assert "valdrics_zombie_potential_savings_usd" not in combined
    assert "valdrics_scans_completed_total" not in combined
    assert "valdrics_llm_cost_usd" not in combined
