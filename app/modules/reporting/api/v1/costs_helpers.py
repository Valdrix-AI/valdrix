from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from app.modules.reporting.domain.anomaly_detection import CostAnomaly

from .costs_models import AcceptanceKpisResponse, CostAnomalyItem, UnitEconomicsMetric

CSV_FORMULA_PREFIXES = ("=", "+", "@", "\t")


def sanitize_csv_cell(value: Any) -> str:
    """Prevent spreadsheet formula injection for untrusted strings."""
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.startswith(CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def validate_anomaly_severity(value: str, supported_severities: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in supported_severities:
        supported = ", ".join(sorted(supported_severities))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported severity '{value}'. Use one of: {supported}",
        )
    return normalized


def anomaly_to_response_item(item: CostAnomaly) -> CostAnomalyItem:
    return CostAnomalyItem(
        day=item.day.isoformat(),
        provider=item.provider,
        account_id=str(item.account_id),
        account_name=item.account_name,
        service=item.service,
        actual_cost_usd=float(item.actual_cost_usd),
        expected_cost_usd=float(item.expected_cost_usd),
        delta_cost_usd=float(item.delta_cost_usd),
        percent_change=item.percent_change,
        kind=item.kind,
        probable_cause=item.probable_cause,
        confidence=item.confidence,
        severity=item.severity,
    )


def build_unit_metrics(
    total_cost: Decimal,
    baseline_total_cost: Decimal,
    threshold_percent: float,
    request_volume: float,
    workload_volume: float,
    customer_volume: float,
) -> list[UnitEconomicsMetric]:
    defs = [
        ("cost_per_request", "Cost Per Request", request_volume),
        ("cost_per_workload", "Cost Per Workload", workload_volume),
        ("cost_per_customer", "Cost Per Customer", customer_volume),
    ]

    metrics: list[UnitEconomicsMetric] = []
    for key, label, denominator in defs:
        if denominator <= 0:
            continue
        current_cpu = float(total_cost / Decimal(str(denominator)))
        baseline_cpu = float(baseline_total_cost / Decimal(str(denominator)))
        if baseline_cpu > 0:
            delta = ((current_cpu - baseline_cpu) / baseline_cpu) * 100
        else:
            delta = 0.0
        is_anomalous = baseline_cpu > 0 and delta >= threshold_percent
        metrics.append(
            UnitEconomicsMetric(
                metric_key=key,
                label=label,
                denominator=round(denominator, 4),
                total_cost=float(total_cost),
                cost_per_unit=round(current_cpu, 6),
                baseline_cost_per_unit=round(baseline_cpu, 6),
                delta_percent=round(delta, 2),
                is_anomalous=is_anomalous,
            )
        )
    return metrics


def render_acceptance_kpi_csv(payload: AcceptanceKpisResponse) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["section", "key", "value"])
    writer.writerow(["meta", "start_date", payload.start_date])
    writer.writerow(["meta", "end_date", payload.end_date])
    writer.writerow(["meta", "tier", payload.tier])
    writer.writerow(["meta", "all_targets_met", payload.all_targets_met])
    writer.writerow(["meta", "available_metrics", payload.available_metrics])
    writer.writerow([])
    writer.writerow(
        ["metric", "key", "label", "available", "target", "actual", "meets_target"]
    )
    for metric in payload.metrics:
        writer.writerow(
            [
                "metric",
                metric.key,
                metric.label,
                metric.available,
                metric.target,
                metric.actual,
                metric.meets_target,
            ]
        )
    return out.getvalue()
