from __future__ import annotations

import math

from prometheus_client import Counter, Gauge
import structlog


COST_RECORD_RETENTION_PURGED_TOTAL = Counter(
    "valdrics_ops_cost_record_retention_purged_total",
    "Total number of cost records purged by retention enforcement",
    ["tenant_tier"],
)

COST_RECORD_RETENTION_LAST_RUN = Gauge(
    "valdrics_ops_cost_record_retention_last_run_deleted",
    "Number of cost records deleted during the most recent retention sweep",
    ["tenant_tier"],
)

RUNTIME_CARBON_EMISSIONS_TOTAL = Counter(
    "valdrics_ops_runtime_carbon_emissions_kg_total",
    "Total runtime emissions measured by the application process in kilograms CO2eq",
)

RUNTIME_CARBON_EMISSIONS_LAST_RUN = Gauge(
    "valdrics_ops_runtime_carbon_emissions_last_run_kg",
    "Carbon emissions measured for the most recent application runtime in kilograms CO2eq",
)


def record_runtime_carbon_emissions(emissions_kg: float | None) -> None:
    """Persist runtime carbon emissions as Prometheus signals."""
    if emissions_kg is None:
        return

    try:
        normalized = float(emissions_kg)
    except (TypeError, ValueError):
        structlog.get_logger().warning(
            "runtime_carbon_emissions_invalid", emissions_kg=emissions_kg
        )
        return

    if not math.isfinite(normalized) or normalized < 0:
        structlog.get_logger().warning(
            "runtime_carbon_emissions_invalid", emissions_kg=emissions_kg
        )
        return

    RUNTIME_CARBON_EMISSIONS_TOTAL.inc(normalized)
    RUNTIME_CARBON_EMISSIONS_LAST_RUN.set(normalized)


def record_cost_retention_purge(tenant_tier: str, deleted_count: int) -> None:
    """Persist plan-aware cost-retention purge results as Prometheus signals."""
    normalized_tier = str(tenant_tier or "unknown").strip().lower() or "unknown"
    normalized_count = int(deleted_count)
    if normalized_count < 0:
        raise ValueError("deleted_count must be >= 0")

    COST_RECORD_RETENTION_LAST_RUN.labels(tenant_tier=normalized_tier).set(
        normalized_count
    )
    if normalized_count:
        COST_RECORD_RETENTION_PURGED_TOTAL.labels(
            tenant_tier=normalized_tier
        ).inc(normalized_count)

