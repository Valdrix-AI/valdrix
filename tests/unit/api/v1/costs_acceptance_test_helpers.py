from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.reporting.api.v1 import costs as costs_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


class ExecResult:
    def __init__(
        self,
        *,
        one_row: object | None = None,
        all_rows: list[object] | None = None,
        scalar_rows: list[object] | None = None,
    ) -> None:
        self._one_row = one_row
        self._all_rows = all_rows or []
        self._scalar_rows = scalar_rows or []
        self._scalars_mode = False

    def one(self) -> object:
        return self._one_row

    def all(self) -> list[object]:
        if self._scalars_mode:
            return self._scalar_rows
        return self._all_rows

    def scalars(self) -> "ExecResult":
        self._scalars_mode = True
        return self


class FakeDB:
    def __init__(
        self,
        *,
        scalar_values: list[object] | None = None,
        execute_values: list[object] | None = None,
    ) -> None:
        self._scalar_iter = iter(scalar_values or [])
        self._execute_iter = iter(execute_values or [])
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def scalar(self, _stmt) -> object:
        value = next(self._scalar_iter)
        if isinstance(value, Exception):
            raise value
        return value

    async def execute(self, _stmt) -> object:
        value = next(self._execute_iter)
        if isinstance(value, Exception):
            raise value
        return value


def user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="acceptance@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def free_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="acceptance-free@valdrics.io",
        role=UserRole.MEMBER,
        tier=PricingTier.FREE,
    )


def sample_payload() -> costs_api.AcceptanceKpisResponse:
    metric = costs_api.AcceptanceKpiMetric(
        key="ingestion_reliability",
        label="Ingestion Reliability + Recency",
        available=True,
        target=">=95.00%",
        actual="99.00%",
        meets_target=True,
        details={},
    )
    return costs_api.AcceptanceKpisResponse(
        start_date="2026-01-01",
        end_date="2026-01-31",
        tier=PricingTier.PRO.value,
        all_targets_met=True,
        available_metrics=1,
        metrics=[metric],
    )


def standard_ingestion_response(
    *,
    window_hours: int = 168,
    total_jobs: int = 8,
    successful_jobs: int = 8,
    failed_jobs: int = 0,
    success_rate_percent: float = 100.0,
    records_ingested: int = 800,
    latest_completed_at: str = "2026-02-20T10:00:00+00:00",
    avg_duration_seconds: float = 120.0,
    p95_duration_seconds: float = 180.0,
) -> costs_api.IngestionSLAResponse:
    return costs_api.IngestionSLAResponse(
        window_hours=window_hours,
        target_success_rate_percent=95.0,
        total_jobs=total_jobs,
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        success_rate_percent=success_rate_percent,
        meets_sla=success_rate_percent >= 95.0,
        latest_completed_at=latest_completed_at,
        avg_duration_seconds=avg_duration_seconds,
        p95_duration_seconds=p95_duration_seconds,
        records_ingested=records_ingested,
    )


def standard_recency_response(
    *,
    provider: str = "aws",
    latest_ingested_at: str = "2026-02-20T09:00:00+00:00",
) -> list[costs_api.ProviderRecencyResponse]:
    return [
        costs_api.ProviderRecencyResponse(
            provider=provider,
            active_connections=1,
            recently_ingested=1,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at=latest_ingested_at,
            recency_target_hours=48,
            meets_recency_target=True,
        )
    ]


def standard_license_metric(
    *,
    available: bool = True,
    actual: str = "100.00%",
    target: str = ">=99.00%",
    meets_target: bool = True,
) -> costs_api.AcceptanceKpiMetric:
    return costs_api.AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=available,
        target=target,
        actual=actual,
        meets_target=meets_target,
        details={},
    )


def unavailable_license_metric() -> costs_api.AcceptanceKpiMetric:
    return standard_license_metric(
        available=False,
        actual="N/A",
        target="N/A",
        meets_target=False,
    )


def standard_unit_settings(
    *,
    default_request_volume: float = 1000.0,
    default_workload_volume: float = 100.0,
    default_customer_volume: float = 20.0,
    anomaly_threshold_percent: float = 20.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        default_request_volume=default_request_volume,
        default_workload_volume=default_workload_volume,
        default_customer_volume=default_customer_volume,
        anomaly_threshold_percent=anomaly_threshold_percent,
    )


def standard_allocation_coverage(
    *,
    target_percentage: float = 90.0,
    coverage_percentage: float = 96.0,
    meets_target: bool = True,
) -> dict[str, float | bool]:
    return {
        "target_percentage": target_percentage,
        "coverage_percentage": coverage_percentage,
        "meets_target": meets_target,
    }


def event_time() -> datetime:
    return datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)
