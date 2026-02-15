"""
Deterministic waste and rightsizing recommendation shaping.

This module converts raw zombie scan categories into a normalized
recommendation payload with:
- detection class
- required action
- confidence score
- estimated monthly savings range (low/mid/high)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DetectionRule:
    detection_class: str
    required_action: str
    base_confidence: float
    savings_factors: tuple[float, float, float]


CATEGORY_RULES: dict[str, DetectionRule] = {
    "idle_instances": DetectionRule(
        detection_class="idle_compute",
        required_action="stop_or_terminate_compute",
        base_confidence=0.82,
        savings_factors=(0.55, 0.75, 0.95),
    ),
    "idle_rds_databases": DetectionRule(
        detection_class="idle_compute",
        required_action="pause_or_rightsize_database",
        base_confidence=0.80,
        savings_factors=(0.45, 0.65, 0.85),
    ),
    "idle_sagemaker_endpoints": DetectionRule(
        detection_class="idle_compute",
        required_action="stop_or_delete_endpoint",
        base_confidence=0.84,
        savings_factors=(0.60, 0.80, 0.95),
    ),
    "underused_nat_gateways": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="consolidate_or_rearchitect_nat",
        base_confidence=0.76,
        savings_factors=(0.25, 0.45, 0.65),
    ),
    "cold_redshift_clusters": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="pause_resize_or_serverless_migrate",
        base_confidence=0.78,
        savings_factors=(0.25, 0.50, 0.70),
    ),
    "idle_saas_subscriptions": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="downgrade_or_cancel_subscription",
        base_confidence=0.79,
        savings_factors=(0.20, 0.40, 0.60),
    ),
    "unused_license_seats": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="reclaim_or_reassign_license_seats",
        base_confidence=0.87,
        savings_factors=(0.35, 0.60, 0.85),
    ),
    "orphan_load_balancers": DetectionRule(
        detection_class="orphaned_assets",
        required_action="decommission_orphaned_load_balancer",
        base_confidence=0.91,
        savings_factors=(0.85, 1.00, 1.05),
    ),
    "unused_elastic_ips": DetectionRule(
        detection_class="orphaned_assets",
        required_action="release_unused_ip",
        base_confidence=0.94,
        savings_factors=(0.90, 1.00, 1.05),
    ),
    "old_snapshots": DetectionRule(
        detection_class="orphaned_assets",
        required_action="expire_or_archive_snapshot",
        base_confidence=0.90,
        savings_factors=(0.80, 0.95, 1.00),
    ),
    "idle_s3_buckets": DetectionRule(
        detection_class="orphaned_assets",
        required_action="archive_or_delete_bucket",
        base_confidence=0.88,
        savings_factors=(0.70, 0.90, 1.00),
    ),
    "stale_ecr_images": DetectionRule(
        detection_class="orphaned_assets",
        required_action="delete_unused_images",
        base_confidence=0.92,
        savings_factors=(0.80, 0.95, 1.00),
    ),
    "unattached_volumes": DetectionRule(
        detection_class="unattached_storage",
        required_action="delete_or_snapshot_then_delete_storage",
        base_confidence=0.96,
        savings_factors=(0.90, 1.00, 1.05),
    ),
    # Expansion beyond classic zombie buckets (containers/serverless/network hygiene).
    "idle_container_clusters": DetectionRule(
        detection_class="idle_compute",
        required_action="scale_down_or_delete_cluster",
        base_confidence=0.83,
        savings_factors=(0.30, 0.55, 0.85),
    ),
    "unused_app_service_plans": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="delete_or_downgrade_app_service_plan",
        base_confidence=0.88,
        savings_factors=(0.50, 0.75, 0.95),
    ),
    "idle_serverless_services": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="remove_reserved_capacity_or_delete_service",
        base_confidence=0.70,
        savings_factors=(0.20, 0.45, 0.70),
    ),
    "idle_serverless_functions": DetectionRule(
        detection_class="over_provisioned_resources",
        required_action="remove_reserved_capacity_or_delete_function",
        base_confidence=0.70,
        savings_factors=(0.20, 0.45, 0.70),
    ),
    "orphan_network_components": DetectionRule(
        detection_class="orphaned_assets",
        required_action="delete_orphan_network_component",
        base_confidence=0.85,
        savings_factors=(0.85, 1.00, 1.05),
    ),
}

_NON_CATEGORY_KEYS = {
    "ai_analysis",
    "architectural_inefficiency",
    "partial_results",
    "scan_timeout",
    "scanned_connections",
    "total_monthly_waste",
    "waste_rightsizing",
}


def build_waste_rightsizing_payload(scan_results: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build deterministic rightsizing recommendations from category scan output.
    """
    recommendations: list[dict[str, Any]] = []
    by_detection_class: dict[str, int] = {}
    savings_low_total = 0.0
    savings_mid_total = 0.0
    savings_high_total = 0.0

    for category, items in scan_results.items():
        if category in _NON_CATEGORY_KEYS or not isinstance(items, list):
            continue

        rule = CATEGORY_RULES.get(category)
        if rule is None:
            continue

        for raw_item in items:
            if not isinstance(raw_item, Mapping):
                continue
            recommendation = _build_recommendation(raw_item, category, rule)
            recommendations.append(recommendation)
            by_detection_class[rule.detection_class] = (
                by_detection_class.get(rule.detection_class, 0) + 1
            )
            savings_low_total += float(
                recommendation["estimated_monthly_savings"]["low"]
            )
            savings_mid_total += float(
                recommendation["estimated_monthly_savings"]["mid"]
            )
            savings_high_total += float(
                recommendation["estimated_monthly_savings"]["high"]
            )

    recommendations.sort(
        key=lambda item: (
            -float(item["estimated_monthly_savings"]["mid"]),
            str(item["resource_id"]),
        )
    )

    return {
        "deterministic": True,
        "recommendations": recommendations,
        "summary": {
            "total_recommendations": len(recommendations),
            "by_detection_class": dict(sorted(by_detection_class.items())),
            "estimated_monthly_savings_range": {
                "low": round(savings_low_total, 2),
                "mid": round(savings_mid_total, 2),
                "high": round(savings_high_total, 2),
            },
        },
    }


def _build_recommendation(
    item: Mapping[str, Any],
    category: str,
    rule: DetectionRule,
) -> dict[str, Any]:
    monthly_cost = _as_non_negative_float(
        item.get("monthly_cost")
        or item.get("monthly_waste")
        or item.get("estimated_monthly_savings")
    )
    savings_low, savings_mid, savings_high = _derive_savings_range(monthly_cost, rule)
    confidence = _derive_confidence(item, rule.base_confidence)

    return {
        "resource_id": str(item.get("resource_id") or item.get("id") or "unknown"),
        "provider": str(item.get("provider") or "unknown"),
        "region": item.get("region"),
        "resource_type": item.get("resource_type"),
        "connection_id": item.get("connection_id"),
        "connection_name": item.get("connection_name"),
        "source_category": category,
        "detection_class": rule.detection_class,
        "required_action": rule.required_action,
        "confidence": confidence,
        "monthly_cost": round(monthly_cost, 2),
        "estimated_monthly_savings": {
            "low": savings_low,
            "mid": savings_mid,
            "high": savings_high,
        },
    }


def _derive_savings_range(
    monthly_cost: float, rule: DetectionRule
) -> tuple[float, float, float]:
    low_factor, mid_factor, high_factor = rule.savings_factors
    return (
        round(monthly_cost * low_factor, 2),
        round(monthly_cost * mid_factor, 2),
        round(monthly_cost * high_factor, 2),
    )


def _derive_confidence(item: Mapping[str, Any], base_confidence: float) -> float:
    confidence = base_confidence

    utilization = _first_number(
        item.get("utilization_percent"),
        item.get("utilization_pct"),
        item.get("avg_cpu_percent"),
    )
    if utilization is not None:
        if utilization <= 5:
            confidence += 0.08
        elif utilization <= 15:
            confidence += 0.04
        elif utilization >= 45:
            confidence -= 0.08

    idle_days = _first_number(
        item.get("days_idle"),
        item.get("idle_days"),
        item.get("days_since_last_active"),
    )
    if idle_days is not None:
        if idle_days >= 30:
            confidence += 0.06
        elif idle_days >= 7:
            confidence += 0.03
        elif idle_days < 3:
            confidence -= 0.05

    if bool(item.get("has_attached_dependencies") or item.get("has_dependencies")):
        confidence -= 0.20
    if bool(item.get("is_production")):
        confidence -= 0.10

    return round(min(0.99, max(0.50, confidence)), 2)


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _as_non_negative_float(value: Any) -> float:
    number = _first_number(value)
    if number is None:
        return 0.0
    return max(0.0, number)
