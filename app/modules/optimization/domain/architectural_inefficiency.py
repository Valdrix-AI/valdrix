"""
Deterministic architectural inefficiency detection.

Signals covered:
- overbuilt availability in non-production workloads
- unjustified multi-zone deployment based on SLO/criticality
- duplicated non-production environments
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


_NON_PRODUCTION_ENVS = {
    "dev",
    "development",
    "qa",
    "test",
    "staging",
    "sandbox",
    "demo",
}
_LOW_CRITICALITY = {"low", "medium", "non_critical", "non-critical", "internal"}
_NON_CATEGORY_KEYS = {
    "ai_analysis",
    "architectural_inefficiency",
    "partial_results",
    "scan_timeout",
    "scanned_connections",
    "total_monthly_waste",
    "waste_rightsizing",
}


def build_architectural_inefficiency_payload(
    scan_results: Mapping[str, Any],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    savings_low_total = 0.0
    savings_mid_total = 0.0
    savings_high_total = 0.0

    resources = list(_iter_resources(scan_results))
    for item in resources:
        zone_count = _zone_count(item)
        environment = _environment(item)
        monthly_cost = _monthly_cost(item)
        if zone_count is None or monthly_cost <= 0:
            continue

        resource_id = str(item.get("resource_id") or item.get("id") or "unknown")
        provider = str(item.get("provider") or "unknown")
        owner = str(item.get("owner") or "unassigned")
        source_category = str(item.get("source_category") or "unknown")
        service = str(
            item.get("service") or item.get("resource_type") or source_category
        )

        if (
            environment in _NON_PRODUCTION_ENVS
            and zone_count >= 2
            and monthly_cost >= 50
        ):
            low, mid, high = _range(monthly_cost, (0.20, 0.35, 0.50))
            confidence = (
                0.80
                + (0.08 if zone_count >= 3 else 0.0)
                + (0.05 if monthly_cost >= 200 else 0.0)
            )
            finding = {
                "finding_type": "overbuilt_availability_pattern",
                "resource_id": resource_id,
                "provider": provider,
                "service": service,
                "source_category": source_category,
                "probable_cause": "Non-production workload is running with multi-zone redundancy.",
                "confidence": round(min(0.99, confidence), 2),
                "risk_label": "medium",
                "required_action": "reduce_redundancy_for_non_production",
                "expected_monthly_savings": {"low": low, "mid": mid, "high": high},
                "policy_route": "review_required",
                "owner": owner,
            }
            _append_finding(
                findings,
                by_type,
                finding,
            )
            savings_low_total += low
            savings_mid_total += mid
            savings_high_total += high

        slo_target = _slo_target(item)
        criticality = (
            str(item.get("business_criticality") or item.get("criticality") or "")
            .strip()
            .lower()
        )
        if (
            zone_count >= 2
            and slo_target is not None
            and slo_target < 99.9
            and criticality in _LOW_CRITICALITY
        ):
            low, mid, high = _range(monthly_cost, (0.15, 0.30, 0.45))
            confidence = 0.78 + (0.05 if slo_target <= 99.5 else 0.0)
            finding = {
                "finding_type": "unjustified_multi_zone_deployment",
                "resource_id": resource_id,
                "provider": provider,
                "service": service,
                "source_category": source_category,
                "probable_cause": "Reliability target does not justify current multi-zone footprint.",
                "confidence": round(min(0.99, confidence), 2),
                "risk_label": "high",
                "required_action": "rightsize_availability_architecture",
                "expected_monthly_savings": {"low": low, "mid": mid, "high": high},
                "policy_route": "escalate_for_architecture_review",
                "owner": owner,
            }
            _append_finding(
                findings,
                by_type,
                finding,
            )
            savings_low_total += low
            savings_mid_total += mid
            savings_high_total += high

    duplicate_finding_tuples = _duplicate_non_production_findings(resources)
    for finding, (low, mid, high) in duplicate_finding_tuples:
        _append_finding(findings, by_type, finding)
        savings_low_total += low
        savings_mid_total += mid
        savings_high_total += high

    findings.sort(
        key=lambda item: (
            -float(item["expected_monthly_savings"]["mid"]),
            str(item["finding_type"]),
            str(item.get("resource_id") or ""),
        )
    )

    return {
        "deterministic": True,
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": dict(sorted(by_type.items())),
            "expected_monthly_savings_range": {
                "low": round(savings_low_total, 2),
                "mid": round(savings_mid_total, 2),
                "high": round(savings_high_total, 2),
            },
        },
    }


def _iter_resources(scan_results: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for category, values in scan_results.items():
        if category in _NON_CATEGORY_KEYS or not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, Mapping):
                continue
            enriched = dict(item)
            enriched["source_category"] = category
            yield enriched


def _duplicate_non_production_findings(
    resources: list[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], tuple[float, float, float]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for item in resources:
        env = _environment(item)
        if env not in _NON_PRODUCTION_ENVS:
            continue
        service = (
            str(
                item.get("workload")
                or item.get("service")
                or item.get("resource_type")
                or item.get("source_category")
                or "unknown"
            )
            .strip()
            .lower()
        )
        provider = str(item.get("provider") or "unknown").strip().lower()
        grouped[(provider, service, env)].append(item)

    findings: list[tuple[dict[str, Any], tuple[float, float, float]]] = []
    for (provider, service, env), items in grouped.items():
        if len(items) < 2:
            continue
        total_cost = sum(_monthly_cost(item) for item in items)
        if total_cost <= 0:
            continue

        duplicate_portion = total_cost * ((len(items) - 1) / len(items))
        low, mid, high = _range(duplicate_portion, (0.25, 0.40, 0.60))
        resource_ids = sorted(
            str(item.get("resource_id") or item.get("id") or "unknown")
            for item in items
        )
        owner = str(items[0].get("owner") or "unassigned")
        finding = {
            "finding_type": "duplicated_non_production_environment",
            "resource_id": resource_ids[0],
            "resource_ids": resource_ids,
            "provider": provider,
            "service": service,
            "source_category": str(items[0].get("source_category") or "unknown"),
            "probable_cause": "Multiple similar non-production resources indicate duplicated environments.",
            "confidence": 0.84,
            "risk_label": "medium",
            "required_action": "consolidate_duplicate_non_production_resources",
            "expected_monthly_savings": {"low": low, "mid": mid, "high": high},
            "policy_route": "review_required",
            "owner": owner,
        }
        findings.append((finding, (low, mid, high)))

    return findings


def _append_finding(
    findings: list[dict[str, Any]],
    by_type: dict[str, int],
    finding: dict[str, Any],
) -> None:
    findings.append(finding)
    finding_type = str(finding["finding_type"])
    by_type[finding_type] = by_type.get(finding_type, 0) + 1


def _zone_count(item: Mapping[str, Any]) -> int | None:
    numeric = _first_number(
        item.get("zone_count"),
        item.get("availability_zone_count"),
    )
    if numeric is not None:
        return int(max(0, round(numeric)))

    zones = item.get("availability_zones") or item.get("zones")
    if isinstance(zones, list):
        normalized = {str(z).strip() for z in zones if str(z).strip()}
        return len(normalized) if normalized else None
    if isinstance(zones, str):
        normalized = {z.strip() for z in zones.split(",") if z.strip()}
        return len(normalized) if normalized else None

    zone = item.get("region") or item.get("zone")
    if bool(item.get("multi_az")):
        return 2
    if zone:
        return 1
    return None


def _environment(item: Mapping[str, Any]) -> str:
    explicit = item.get("environment")
    if explicit:
        return str(explicit).strip().lower()

    tags = item.get("tags")
    if isinstance(tags, Mapping):
        for key in ("environment", "env", "stage"):
            value = tags.get(key)
            if value:
                return str(value).strip().lower()
    return "unknown"


def _monthly_cost(item: Mapping[str, Any]) -> float:
    number = _first_number(
        item.get("monthly_cost"),
        item.get("monthly_waste"),
        item.get("estimated_monthly_savings"),
    )
    if number is None:
        return 0.0
    return max(0.0, number)


def _slo_target(item: Mapping[str, Any]) -> float | None:
    return _first_number(
        item.get("slo_target"),
        item.get("slo"),
        item.get("availability_slo"),
    )


def _range(
    value: float, factors: tuple[float, float, float]
) -> tuple[float, float, float]:
    low_factor, mid_factor, high_factor = factors
    return (
        round(value * low_factor, 2),
        round(value * mid_factor, 2),
        round(value * high_factor, 2),
    )


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
