from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.background_job import JobStatus
from app.modules.reporting.api.v1 import costs_metrics
from app.modules.reporting.api.v1.costs_metrics import (
    AcceptanceKpiMetric,
    IngestionSLAResponse,
    ProviderRecencyResponse,
)


def _scalars_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _one_result(item: object) -> MagicMock:
    result = MagicMock()
    result.one.return_value = item
    return result


def _all_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


def test_settings_to_response_and_connection_active_delegate() -> None:
    settings = SimpleNamespace(
        id=uuid4(),
        default_request_volume=Decimal("100"),
        default_workload_volume=Decimal("20"),
        default_customer_volume=Decimal("5"),
        anomaly_threshold_percent=Decimal("35"),
    )

    out = costs_metrics.settings_to_response(settings)
    assert out.default_request_volume == 100.0
    assert out.anomaly_threshold_percent == 35.0

    connection = SimpleNamespace(status="active")
    with patch.object(costs_metrics, "is_connection_active", return_value=True) as mocked:
        assert costs_metrics.is_connection_active_state(connection) is True
    mocked.assert_called_once_with(connection)


@pytest.mark.asyncio
async def test_get_or_create_unit_settings_returns_existing() -> None:
    existing = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.scalar = AsyncMock(return_value=existing)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    out = await costs_metrics.get_or_create_unit_settings(db, uuid4())

    assert out is existing
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_unit_settings_creates_defaults() -> None:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    tenant_id = uuid4()
    out = await costs_metrics.get_or_create_unit_settings(db, tenant_id)

    assert out.tenant_id == tenant_id
    db.add.assert_called_once_with(out)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(out)


@pytest.mark.asyncio
async def test_window_total_cost_handles_provider_filter_and_none_scalar() -> None:
    result_zero = MagicMock()
    result_zero.scalar_one_or_none.return_value = None
    result_value = MagicMock()
    result_value.scalar_one_or_none.return_value = Decimal("12.34")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result_zero, result_value])
    tenant_id = uuid4()

    zero_total = await costs_metrics.window_total_cost(
        db=db,
        tenant_id=tenant_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        provider="aws",
    )
    nonzero_total = await costs_metrics.window_total_cost(
        db=db,
        tenant_id=tenant_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        provider=None,
    )

    assert zero_total == Decimal("0")
    assert nonzero_total == Decimal("12.34")
    assert db.execute.await_count == 2


def test_build_provider_recency_summary_handles_naive_stale_never_and_recent() -> None:
    now = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)
    naive_recent = datetime(2026, 2, 26, 10, 0)

    connections = [
        SimpleNamespace(status="active", last_ingested_at=naive_recent),
        SimpleNamespace(
            status="active",
            last_ingested_at=now - timedelta(hours=96),
        ),
        SimpleNamespace(status="active", last_ingested_at=None),
        SimpleNamespace(status="inactive", last_ingested_at=now - timedelta(hours=1)),
    ]

    summary = costs_metrics.build_provider_recency_summary(
        "aws",
        connections,
        now=now,
        recency_target_hours=48,
    )

    assert summary.provider == "aws"
    assert summary.active_connections == 3
    assert summary.recently_ingested == 1
    assert summary.stale_connections == 1
    assert summary.never_ingested == 1
    assert summary.latest_ingested_at is not None
    assert summary.meets_recency_target is False


@pytest.mark.asyncio
async def test_compute_provider_recency_summaries_iterates_all_provider_models() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalars_result([]) for _ in range(7)])

    seen: list[tuple[str, int]] = []

    def _fake_builder(
        provider: str,
        connections: list[object],
        *,
        now: datetime,
        recency_target_hours: int,
    ) -> ProviderRecencyResponse:
        seen.append((provider, recency_target_hours))
        return ProviderRecencyResponse(
            provider=provider,
            active_connections=len(connections),
            recently_ingested=0,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at=None,
            recency_target_hours=recency_target_hours,
            meets_recency_target=False,
        )

    with patch.object(costs_metrics, "build_provider_recency_summary", side_effect=_fake_builder):
        summaries = await costs_metrics.compute_provider_recency_summaries(
            db, tenant_id, recency_target_hours=24
        )

    assert len(summaries) == 7
    assert [item.provider for item in summaries] == [
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    ]
    assert all(hours == 24 for _, hours in seen)
    assert db.execute.await_count == 7


@pytest.mark.asyncio
async def test_compute_ingestion_sla_metrics_with_jobs_and_durations() -> None:
    now = datetime.now(timezone.utc)
    jobs = [
        SimpleNamespace(
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=20),
            completed_at=now - timedelta(minutes=10),
            result={"ingested": 12.9},
        ),
        SimpleNamespace(
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=6),  # negative duration ignored
            result={"ingested": "bad"},
        ),
        SimpleNamespace(
            status=JobStatus.DEAD_LETTER.value,
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=30),
            completed_at=now - timedelta(minutes=28),
            result={},
        ),
        SimpleNamespace(
            status=JobStatus.FAILED.value,
            created_at=now - timedelta(hours=1),
            started_at=None,
            completed_at=None,
            result=None,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result(jobs))

    out = await costs_metrics.compute_ingestion_sla_metrics(
        db=db,
        tenant_id=uuid4(),
        window_hours=6,
        target_success_rate_percent=40.0,
    )

    assert isinstance(out, IngestionSLAResponse)
    assert out.total_jobs == 4
    assert out.successful_jobs == 2
    assert out.failed_jobs == 2
    assert out.success_rate_percent == 50.0
    assert out.meets_sla is True
    assert out.records_ingested == 12
    assert out.avg_duration_seconds == 360.0
    assert out.p95_duration_seconds == 600.0
    assert out.latest_completed_at is not None


@pytest.mark.asyncio
async def test_compute_ingestion_sla_metrics_empty_window_defaults() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    out = await costs_metrics.compute_ingestion_sla_metrics(
        db=db,
        tenant_id=uuid4(),
        window_hours=24,
        target_success_rate_percent=95.0,
    )

    assert out.total_jobs == 0
    assert out.success_rate_percent == 0.0
    assert out.meets_sla is False
    assert out.avg_duration_seconds is None
    assert out.p95_duration_seconds is None
    assert out.latest_completed_at is None


@pytest.mark.asyncio
async def test_compute_license_governance_kpi_no_active_connections() -> None:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=0)
    db.execute = AsyncMock()

    metric = await costs_metrics.compute_license_governance_kpi(
        db=db,
        tenant_id=uuid4(),
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    assert isinstance(metric, AcceptanceKpiMetric)
    assert metric.available is False
    assert metric.meets_target is False
    assert metric.details["active_license_connections"] == 0
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_compute_license_governance_kpi_active_connections_and_cycle_time() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.scalar = AsyncMock(return_value=2)

    counts_row = SimpleNamespace(
        total_requests=10,
        completed_requests=8,
        failed_requests=1,
        in_flight_requests=1,
    )
    naive_created = datetime(2026, 2, 3, 10, 0, 0)
    naive_executed = datetime(2026, 2, 3, 16, 0, 0)
    aware_created = datetime(2026, 2, 5, 8, 0, 0, tzinfo=timezone.utc)
    aware_executed = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc)

    db.execute = AsyncMock(
        side_effect=[
            _one_result(counts_row),
            _all_result(
                [
                    (naive_created, naive_executed),
                    (aware_created, aware_executed),
                    (None, aware_executed),
                    (aware_executed, aware_created),  # executed before created -> ignored
                ]
            ),
        ]
    )

    metric = await costs_metrics.compute_license_governance_kpi(
        db=db,
        tenant_id=tenant_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    assert metric.available is True
    assert metric.meets_target is True
    assert metric.details["total_requests"] == 10
    assert metric.details["completed_requests"] == 8
    assert metric.details["failed_requests"] == 1
    assert metric.details["in_flight_requests"] == 1
    assert metric.details["completion_rate_percent"] == 80.0
    assert metric.details["failure_rate_percent"] == 10.0
    assert metric.details["in_flight_ratio_percent"] == 10.0
    assert metric.details["avg_time_to_complete_hours"] == 5.0
    assert "80.00% completion" in metric.actual

