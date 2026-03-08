from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.api.v1 import costs as costs_api
from tests.unit.api.v1.costs_acceptance_test_helpers import (
    ExecResult,
    FakeDB,
    event_time,
    sample_payload,
    standard_ingestion_response,
    standard_license_metric,
    standard_recency_response,
    standard_unit_settings,
    user,
)


@pytest.mark.asyncio
async def test_acceptance_kpis_endpoints_direct_branches() -> None:
    db = FakeDB()

    with patch.object(
        costs_api,
        "_compute_acceptance_kpis_payload",
        new=AsyncMock(return_value=sample_payload()),
    ):
        csv_response = await costs_api.get_acceptance_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            response_format="csv",
            current_user=user(),
            db=db,  # type: ignore[arg-type]
        )

    assert "text/csv" in csv_response.media_type
    assert "attachment; filename=" in csv_response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_capture_and_list_acceptance_evidence_direct_paths() -> None:
    current_user = user()
    payload = sample_payload()
    captured_at = event_time()
    db = FakeDB(
        execute_values=[
            ExecResult(
                scalar_rows=[
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-1",
                        event_timestamp=captured_at,
                        actor_id=current_user.id,
                        actor_email=current_user.email,
                        success=True,
                        details={"acceptance_kpis": payload.model_dump()},
                    ),
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-2",
                        event_timestamp=captured_at,
                        actor_id=current_user.id,
                        actor_email=current_user.email,
                        success=True,
                        details={"acceptance_kpis": "invalid"},
                    ),
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-3",
                        event_timestamp=captured_at,
                        actor_id=current_user.id,
                        actor_email=current_user.email,
                        success=True,
                        details={"acceptance_kpis": {"unexpected": "shape"}},
                    ),
                ]
            )
        ]
    )

    class AuditLogger:
        def __init__(self, **_kwargs) -> None:
            pass

        async def log(self, **_kwargs):
            return SimpleNamespace(id=uuid4(), event_timestamp=captured_at)

    with (
        patch.object(
            costs_api,
            "_compute_acceptance_kpis_payload",
            new=AsyncMock(return_value=payload),
        ),
        patch("app.modules.governance.domain.security.audit_log.AuditLogger", AuditLogger),
    ):
        captured = await costs_api.capture_acceptance_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=current_user,
            db=db,  # type: ignore[arg-type]
        )
        listed = await costs_api.list_acceptance_kpi_evidence(
            limit=100,
            current_user=current_user,
            db=db,  # type: ignore[arg-type]
        )

    assert captured.status == "captured"
    assert captured.acceptance_kpis.start_date == "2026-01-01"
    assert listed.total == 1
    assert listed.items[0].acceptance_kpis.end_date == "2026-01-31"


@pytest.mark.asyncio
async def test_unit_economics_settings_endpoints_direct_paths() -> None:
    settings_row = SimpleNamespace(
        id=uuid4(),
        default_request_volume=1000.0,
        default_workload_volume=100.0,
        default_customer_volume=20.0,
        anomaly_threshold_percent=15.0,
    )
    db = FakeDB()

    with patch.object(
        costs_api,
        "_get_or_create_unit_settings",
        new=AsyncMock(return_value=settings_row),
    ):
        read_response = await costs_api.get_unit_economics_settings(
            user=user(),
            db=db,  # type: ignore[arg-type]
        )
        update_response = await costs_api.update_unit_economics_settings(
            payload=costs_api.UnitEconomicsSettingsUpdate(default_request_volume=1200.0),
            user=user(),
            db=db,  # type: ignore[arg-type]
        )

    assert read_response.default_request_volume == 1000.0
    assert update_response.default_request_volume == 1200.0


@pytest.mark.asyncio
async def test_get_unit_economics_alert_paths() -> None:
    anomaly_metric = costs_api.UnitEconomicsMetric(
        metric_key="cost_per_request",
        label="Cost / Request",
        denominator=1000.0,
        total_cost=100.0,
        cost_per_unit=0.1,
        baseline_cost_per_unit=0.05,
        delta_percent=100.0,
        is_anomalous=True,
    )

    for send_alert_side_effect, expected in ((None, True), (RuntimeError("boom"), False)):
        db = FakeDB()
        with (
            patch.object(
                costs_api,
                "_get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=standard_unit_settings(anomaly_threshold_percent=15.0)
                ),
            ),
            patch.object(
                costs_api,
                "_window_total_cost",
                new=AsyncMock(side_effect=[Decimal("100"), Decimal("90")]),
            ),
            patch.object(
                costs_api,
                "_build_unit_metrics",
                return_value=[anomaly_metric],
            ),
            patch.object(
                costs_api.NotificationDispatcher,
                "send_alert",
                new=AsyncMock(side_effect=send_alert_side_effect),
            ),
        ):
            response = await costs_api.get_unit_economics(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                provider=None,
                request_volume=None,
                workload_volume=None,
                customer_volume=None,
                alert_on_anomaly=True,
                user=user(),
                db=db,  # type: ignore[arg-type]
            )

        assert response.anomaly_count == 1
        assert response.alert_dispatched is expected


def test_costs_wrapper_delegates_and_provider_filter_edge_paths() -> None:
    assert costs_api._normalize_provider_filter(None) is None
    assert costs_api._normalize_provider_filter("   ") is None

    with pytest.raises(costs_api.HTTPException) as exc_info:
        costs_api._normalize_provider_filter("oracle")
    assert exc_info.value.status_code == 400

    connection = SimpleNamespace(status="active")
    with patch.object(costs_api, "_is_connection_active_impl", return_value=True) as mock_impl:
        assert costs_api._is_connection_active(connection) is True
    mock_impl.assert_called_once_with(connection)

    with patch.object(
        costs_api,
        "_build_provider_recency_summary_impl",
        return_value=SimpleNamespace(provider="aws"),
    ) as mock_impl:
        summary = costs_api._build_provider_recency_summary(
            "aws",
            [],
            now=date(2026, 2, 26),
            recency_target_hours=48,
        )
    assert summary.provider == "aws"
    mock_impl.assert_called_once()


@pytest.mark.asyncio
async def test_costs_async_wrapper_delegate_paths() -> None:
    db = FakeDB()
    tenant_id = uuid4()

    with (
        patch.object(
            costs_api,
            "_compute_provider_recency_summaries_impl",
            new=AsyncMock(return_value=standard_recency_response()),
        ) as mock_recency,
        patch.object(
            costs_api,
            "_compute_ingestion_sla_metrics_impl",
            new=AsyncMock(
                return_value=standard_ingestion_response(
                    window_hours=24,
                    total_jobs=1,
                    successful_jobs=1,
                    records_ingested=5,
                    avg_duration_seconds=10.0,
                    p95_duration_seconds=10.0,
                )
            ),
        ) as mock_ingestion,
        patch.object(
            costs_api,
            "_compute_license_governance_kpi_impl",
            new=AsyncMock(return_value=standard_license_metric()),
        ) as mock_license,
    ):
        assert await costs_api._compute_provider_recency_summaries(
            db,
            tenant_id,
            recency_target_hours=48,
        ) == standard_recency_response()
        assert await costs_api._compute_ingestion_sla_metrics(
            db,
            tenant_id,
            window_hours=24,
            target_success_rate_percent=95.0,
        ) == standard_ingestion_response(
            window_hours=24,
            total_jobs=1,
            successful_jobs=1,
            records_ingested=5,
            avg_duration_seconds=10.0,
            p95_duration_seconds=10.0,
        )
        assert await costs_api._compute_license_governance_kpi(
            db=db,
            tenant_id=tenant_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ) == standard_license_metric()

    mock_recency.assert_awaited_once()
    mock_ingestion.assert_awaited_once()
    mock_license.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_costs_endpoint_validation_and_json_branches() -> None:
    current_user = user()
    db = FakeDB()

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_cost_attribution_coverage(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            db=db,  # type: ignore[arg-type]
            current_user=current_user,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_canonical_quality(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            provider=None,
            notify_on_breach=False,
            db=db,  # type: ignore[arg-type]
            current_user=current_user,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_restatement_history(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            provider=None,
            response_format="json",
            user=current_user,
            db=db,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 400

    with patch.object(
        costs_api,
        "_compute_acceptance_kpis_payload",
        new=AsyncMock(return_value=sample_payload()),
    ):
        out = await costs_api.get_acceptance_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            response_format="json",
            current_user=current_user,
            db=db,  # type: ignore[arg-type]
        )

    assert out == sample_payload()


@pytest.mark.asyncio
async def test_get_costs_small_dataset_returns_dashboard_summary_directly() -> None:
    current_user = user()
    db = FakeDB()
    response = SimpleNamespace(status_code=200)
    expected = {"summary": {"total_cost": 123.45}}

    with (
        patch.object(
            costs_api.CostAggregator,
            "count_records",
            new=AsyncMock(return_value=42),
        ),
        patch.object(
            costs_api.CostAggregator,
            "get_dashboard_summary",
            new=AsyncMock(return_value=expected),
        ) as mock_summary,
    ):
        out = await costs_api.get_costs(
            response=response,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            db=db,  # type: ignore[arg-type]
            current_user=current_user,
        )

    assert out == expected
    assert response.status_code == 200
    mock_summary.assert_awaited_once_with(
        db,
        current_user.tenant_id,
        date(2026, 1, 1),
        date(2026, 1, 31),
        "aws",
    )
