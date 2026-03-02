from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.api.v1 import costs as costs_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


class _ExecResult:
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

    def scalars(self) -> "_ExecResult":
        self._scalars_mode = True
        return self


class _FakeDB:
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


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="acceptance@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _free_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="acceptance-free@valdrics.io",
        role=UserRole.MEMBER,
        tier=PricingTier.FREE,
    )


def _sample_payload() -> costs_api.AcceptanceKpisResponse:
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


@pytest.mark.asyncio
async def test_compute_acceptance_payload_handles_zero_ledger_records() -> None:
    user = _user()
    db = _FakeDB(scalar_values=[5, 1, 0])
    ingestion = costs_api.IngestionSLAResponse(
        window_hours=168,
        target_success_rate_percent=95.0,
        total_jobs=8,
        successful_jobs=8,
        failed_jobs=0,
        success_rate_percent=100.0,
        meets_sla=True,
        latest_completed_at="2026-02-20T10:00:00+00:00",
        avg_duration_seconds=120.0,
        p95_duration_seconds=180.0,
        records_ingested=800,
    )
    recency = [
        costs_api.ProviderRecencyResponse(
            provider="aws",
            active_connections=1,
            recently_ingested=1,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at="2026-02-20T09:00:00+00:00",
            recency_target_hours=48,
            meets_recency_target=True,
        )
    ]
    license_metric = costs_api.AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=True,
        target=">=99.00%",
        actual="100.00%",
        meets_target=True,
        details={},
    )

    with (
        patch.object(
            costs_api, "_compute_ingestion_sla_metrics", new=AsyncMock(return_value=ingestion)
        ),
        patch.object(
            costs_api,
            "_compute_provider_recency_summaries",
            new=AsyncMock(return_value=recency),
        ),
        patch.object(
            costs_api, "_compute_license_governance_kpi", new=AsyncMock(return_value=license_metric)
        ),
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
            new=AsyncMock(
                return_value={
                    "target_percentage": 90.0,
                    "coverage_percentage": 96.0,
                    "meets_target": True,
                }
            ),
        ),
        patch.object(
            costs_api,
            "_get_or_create_unit_settings",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    default_request_volume=1000.0,
                    default_workload_volume=100.0,
                    default_customer_volume=20.0,
                    anomaly_threshold_percent=20.0,
                )
            ),
        ),
        patch.object(
            costs_api,
            "_window_total_cost",
            new=AsyncMock(side_effect=[Decimal("1000"), Decimal("900")]),
        ),
        patch.object(
            costs_api,
            "get_settings",
            return_value=SimpleNamespace(ENCRYPTION_KEY="k", KDF_SALT="s"),
        ),
    ):
        payload = await costs_api._compute_acceptance_kpis_payload(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )

    by_key = {metric.key: metric for metric in payload.metrics}
    assert by_key["tenant_isolation_proof"].available is True
    assert by_key["encryption_health_proof"].meets_target is True
    assert by_key["user_access_review_proof"].actual == "5 active users"
    assert by_key["ledger_normalization_coverage"].available is False
    assert by_key["canonical_mapping_coverage"].actual == "No cost records in window"


@pytest.mark.asyncio
async def test_compute_acceptance_payload_builds_ledger_breakdown_and_unmapped_signatures() -> None:
    user = _user()
    db = _FakeDB(
        scalar_values=[2, 1, 10],
        execute_values=[
            _ExecResult(
                one_row=SimpleNamespace(
                    total_records=10,
                    normalized_records=8,
                    mapped_records=7,
                    unknown_service_records=1,
                    invalid_currency_records=1,
                    usage_unit_missing_records=0,
                )
            ),
            _ExecResult(
                all_rows=[
                    SimpleNamespace(
                        provider="aws",
                        total_records=6,
                        normalized_records=5,
                        mapped_records=5,
                    ),
                    SimpleNamespace(
                        provider="saas",
                        total_records=4,
                        normalized_records=3,
                        mapped_records=2,
                    ),
                ]
            ),
            _ExecResult(
                all_rows=[
                    SimpleNamespace(
                        provider="aws",
                        service="AmazonEC2",
                        usage_type="BoxUsage:t3.micro",
                        record_count=3,
                        first_seen=datetime(2026, 1, 3, tzinfo=timezone.utc),
                        last_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
                    )
                ]
            ),
        ],
    )
    ingestion = costs_api.IngestionSLAResponse(
        window_hours=168,
        target_success_rate_percent=95.0,
        total_jobs=8,
        successful_jobs=8,
        failed_jobs=0,
        success_rate_percent=100.0,
        meets_sla=True,
        latest_completed_at="2026-02-20T10:00:00+00:00",
        avg_duration_seconds=120.0,
        p95_duration_seconds=180.0,
        records_ingested=800,
    )
    recency = [
        costs_api.ProviderRecencyResponse(
            provider="aws",
            active_connections=1,
            recently_ingested=1,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at="2026-02-20T09:00:00+00:00",
            recency_target_hours=48,
            meets_recency_target=True,
        )
    ]
    license_metric = costs_api.AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=True,
        target=">=99.00%",
        actual="100.00%",
        meets_target=True,
        details={},
    )

    with (
        patch.object(
            costs_api, "_compute_ingestion_sla_metrics", new=AsyncMock(return_value=ingestion)
        ),
        patch.object(
            costs_api,
            "_compute_provider_recency_summaries",
            new=AsyncMock(return_value=recency),
        ),
        patch.object(
            costs_api, "_compute_license_governance_kpi", new=AsyncMock(return_value=license_metric)
        ),
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
            new=AsyncMock(
                return_value={
                    "target_percentage": 90.0,
                    "coverage_percentage": 96.0,
                    "meets_target": True,
                }
            ),
        ),
        patch.object(
            costs_api,
            "_get_or_create_unit_settings",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    default_request_volume=1000.0,
                    default_workload_volume=100.0,
                    default_customer_volume=20.0,
                    anomaly_threshold_percent=20.0,
                )
            ),
        ),
        patch.object(
            costs_api,
            "_window_total_cost",
            new=AsyncMock(side_effect=[Decimal("1000"), Decimal("900")]),
        ),
        patch.object(
            costs_api,
            "get_settings",
            return_value=SimpleNamespace(ENCRYPTION_KEY="k", KDF_SALT="s"),
        ),
    ):
        payload = await costs_api._compute_acceptance_kpis_payload(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )

    by_key = {metric.key: metric for metric in payload.metrics}
    ledger = by_key["ledger_normalization_coverage"]
    canonical = by_key["canonical_mapping_coverage"]
    assert ledger.available is True
    assert ledger.actual == "80.00%"
    assert ledger.details["provider_breakdown"][0]["provider"] == "aws"
    assert canonical.actual == "70.00%"
    assert canonical.details["top_unmapped_signatures"][0]["service"] == "AmazonEC2"


@pytest.mark.asyncio
async def test_compute_acceptance_payload_handles_ledger_query_exception() -> None:
    user = _user()
    db = _FakeDB(scalar_values=[1, 0, RuntimeError("ledger query failed")])
    ingestion = costs_api.IngestionSLAResponse(
        window_hours=168,
        target_success_rate_percent=95.0,
        total_jobs=1,
        successful_jobs=1,
        failed_jobs=0,
        success_rate_percent=100.0,
        meets_sla=True,
        latest_completed_at="2026-02-20T10:00:00+00:00",
        avg_duration_seconds=10.0,
        p95_duration_seconds=10.0,
        records_ingested=1,
    )
    recency = [
        costs_api.ProviderRecencyResponse(
            provider="aws",
            active_connections=1,
            recently_ingested=1,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at="2026-02-20T09:00:00+00:00",
            recency_target_hours=48,
            meets_recency_target=True,
        )
    ]

    with (
        patch.object(
            costs_api, "_compute_ingestion_sla_metrics", new=AsyncMock(return_value=ingestion)
        ),
        patch.object(
            costs_api,
            "_compute_provider_recency_summaries",
            new=AsyncMock(return_value=recency),
        ),
        patch.object(
            costs_api,
            "_compute_license_governance_kpi",
            new=AsyncMock(
                return_value=costs_api.AcceptanceKpiMetric(
                    key="license_governance_reliability",
                    label="License Governance Reliability",
                    available=False,
                    target="N/A",
                    actual="N/A",
                    meets_target=False,
                    details={},
                )
            ),
        ),
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
            new=AsyncMock(return_value={"coverage_percentage": 0, "meets_target": False}),
        ),
        patch.object(
            costs_api,
            "_get_or_create_unit_settings",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    default_request_volume=1.0,
                    default_workload_volume=1.0,
                    default_customer_volume=1.0,
                    anomaly_threshold_percent=20.0,
                )
            ),
        ),
        patch.object(
            costs_api,
            "_window_total_cost",
            new=AsyncMock(side_effect=[Decimal("1"), Decimal("1")]),
        ),
        patch.object(
            costs_api,
            "get_settings",
            return_value=SimpleNamespace(ENCRYPTION_KEY="", KDF_SALT=""),
        ),
    ):
        payload = await costs_api._compute_acceptance_kpis_payload(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=1,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )

    by_key = {metric.key: metric for metric in payload.metrics}
    assert by_key["ledger_normalization_coverage"].available is False
    assert by_key["encryption_health_proof"].actual == "Degraded"


@pytest.mark.asyncio
async def test_acceptance_kpis_endpoints_direct_branches() -> None:
    user = _user()
    payload = _sample_payload()
    db = _FakeDB()

    with patch.object(
        costs_api,
        "_compute_acceptance_kpis_payload",
        new=AsyncMock(return_value=payload),
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
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )
        assert "text/csv" in csv_response.media_type
        assert "attachment; filename=" in csv_response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_capture_and_list_acceptance_evidence_direct_paths() -> None:
    user = _user()
    payload = _sample_payload()
    event_time = datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        execute_values=[
            _ExecResult(
                scalar_rows=[
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-1",
                        event_timestamp=event_time,
                        actor_id=user.id,
                        actor_email=user.email,
                        success=True,
                        details={"acceptance_kpis": payload.model_dump()},
                    ),
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-2",
                        event_timestamp=event_time,
                        actor_id=user.id,
                        actor_email=user.email,
                        success=True,
                        details={"acceptance_kpis": "invalid"},
                    ),
                    SimpleNamespace(
                        id=uuid4(),
                        correlation_id="run-3",
                        event_timestamp=event_time,
                        actor_id=user.id,
                        actor_email=user.email,
                        success=True,
                        details={"acceptance_kpis": {"unexpected": "shape"}},
                    ),
                ]
            )
        ]
    )

    class _AuditLogger:
        def __init__(self, **_kwargs) -> None:
            pass

        async def log(self, **_kwargs):
            return SimpleNamespace(id=uuid4(), event_timestamp=event_time)

    with (
        patch.object(
            costs_api,
            "_compute_acceptance_kpis_payload",
            new=AsyncMock(return_value=payload),
        ),
        patch("app.modules.governance.domain.security.audit_log.AuditLogger", _AuditLogger),
    ):
        captured = await costs_api.capture_acceptance_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=168,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )
        assert captured.status == "captured"
        assert captured.acceptance_kpis.start_date == "2026-01-01"

        listed = await costs_api.list_acceptance_kpi_evidence(
            limit=100,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )
        assert listed.total == 1
        assert listed.items[0].acceptance_kpis.end_date == "2026-01-31"


@pytest.mark.asyncio
async def test_unit_economics_settings_endpoints_direct_paths() -> None:
    user = _user()
    settings_row = SimpleNamespace(
        id=uuid4(),
        default_request_volume=1000.0,
        default_workload_volume=100.0,
        default_customer_volume=20.0,
        anomaly_threshold_percent=15.0,
    )
    db = _FakeDB()

    with patch.object(
        costs_api,
        "_get_or_create_unit_settings",
        new=AsyncMock(return_value=settings_row),
    ):
        read_response = await costs_api.get_unit_economics_settings(
            user=user,
            db=db,  # type: ignore[arg-type]
        )
        assert read_response.default_request_volume == 1000.0

        update_response = await costs_api.update_unit_economics_settings(
            payload=costs_api.UnitEconomicsSettingsUpdate(default_request_volume=1200.0),
            user=user,
            db=db,  # type: ignore[arg-type]
        )
        assert update_response.default_request_volume == 1200.0


@pytest.mark.asyncio
async def test_get_unit_economics_alert_paths() -> None:
    user = _user()
    settings_row = SimpleNamespace(
        id=uuid4(),
        default_request_volume=1000.0,
        default_workload_volume=100.0,
        default_customer_volume=20.0,
        anomaly_threshold_percent=15.0,
    )
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
        db = _FakeDB()
        with (
            patch.object(
                costs_api,
                "_get_or_create_unit_settings",
                new=AsyncMock(return_value=settings_row),
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
                user=user,
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
            now=datetime(2026, 2, 26, tzinfo=timezone.utc),
            recency_target_hours=48,
        )
    assert summary.provider == "aws"
    mock_impl.assert_called_once()


@pytest.mark.asyncio
async def test_costs_async_wrapper_delegate_paths() -> None:
    db = _FakeDB()
    tenant_id = uuid4()
    recency_payload = [
        costs_api.ProviderRecencyResponse(
            provider="aws",
            active_connections=1,
            recently_ingested=1,
            stale_connections=0,
            never_ingested=0,
            latest_ingested_at="2026-02-20T09:00:00+00:00",
            recency_target_hours=48,
            meets_recency_target=True,
        )
    ]
    ingestion_payload = costs_api.IngestionSLAResponse(
        window_hours=24,
        target_success_rate_percent=95.0,
        total_jobs=1,
        successful_jobs=1,
        failed_jobs=0,
        success_rate_percent=100.0,
        meets_sla=True,
        latest_completed_at="2026-02-20T10:00:00+00:00",
        avg_duration_seconds=10.0,
        p95_duration_seconds=10.0,
        records_ingested=5,
    )
    license_metric = costs_api.AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=True,
        target=">=99.00%",
        actual="100.00%",
        meets_target=True,
        details={},
    )

    with (
        patch.object(
            costs_api,
            "_compute_provider_recency_summaries_impl",
            new=AsyncMock(return_value=recency_payload),
        ) as mock_recency,
        patch.object(
            costs_api,
            "_compute_ingestion_sla_metrics_impl",
            new=AsyncMock(return_value=ingestion_payload),
        ) as mock_ingestion,
        patch.object(
            costs_api,
            "_compute_license_governance_kpi_impl",
            new=AsyncMock(return_value=license_metric),
        ) as mock_license,
    ):
        assert await costs_api._compute_provider_recency_summaries(
            db, tenant_id, recency_target_hours=48
        ) == recency_payload
        assert await costs_api._compute_ingestion_sla_metrics(
            db, tenant_id, window_hours=24, target_success_rate_percent=95.0
        ) == ingestion_payload
        assert await costs_api._compute_license_governance_kpi(
            db=db,
            tenant_id=tenant_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ) == license_metric

    mock_recency.assert_awaited_once()
    mock_ingestion.assert_awaited_once()
    mock_license.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_costs_endpoint_validation_and_json_branches() -> None:
    user = _user()
    db = _FakeDB()

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_cost_attribution_coverage(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            db=db,  # type: ignore[arg-type]
            current_user=user,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_canonical_quality(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            provider=None,
            notify_on_breach=False,
            db=db,  # type: ignore[arg-type]
            current_user=user,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api.get_restatement_history(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            provider=None,
            response_format="json",
            user=user,
            db=db,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 400

    payload = _sample_payload()
    with patch.object(
        costs_api,
        "_compute_acceptance_kpis_payload",
        new=AsyncMock(return_value=payload),
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
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )
    assert out is payload


@pytest.mark.asyncio
async def test_canonical_quality_alert_failure_branch_records_error() -> None:
    user = _user()
    db = _FakeDB()
    quality = {
        "target_percentage": 99.0,
        "total_records": 100,
        "mapped_percentage": 85.0,
        "unmapped_records": 15,
        "meets_target": False,
        "status": "warning",
    }

    with (
        patch.object(
            costs_api.CostAggregator,
            "get_canonical_data_quality",
            new=AsyncMock(return_value=quality),
        ),
        patch.object(
            costs_api.NotificationDispatcher,
            "send_alert",
            new=AsyncMock(side_effect=RuntimeError("notify-failed")),
        ),
    ):
        out = await costs_api.get_canonical_quality(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            notify_on_breach=True,
            db=db,  # type: ignore[arg-type]
            current_user=user,
        )

    assert out["alert_triggered"] is False
    assert out["alert_error"] == "notify-failed"


@pytest.mark.asyncio
async def test_compute_acceptance_payload_invalid_window_and_unavailable_feature_branches() -> None:
    user = _free_user()

    with pytest.raises(costs_api.HTTPException) as exc_info:
        await costs_api._compute_acceptance_kpis_payload(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            ingestion_window_hours=24,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=_FakeDB(),  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 400

    db = _FakeDB(scalar_values=[0, 0, 0])
    license_metric = costs_api.AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=False,
        target="N/A",
        actual="N/A",
        meets_target=False,
        details={},
    )

    def _feature_disabled_for_analytics(_tier, feature):
        return feature not in {
            costs_api.FeatureFlag.INGESTION_SLA,
            costs_api.FeatureFlag.CHARGEBACK,
            costs_api.FeatureFlag.UNIT_ECONOMICS,
        }

    with (
        patch.object(
            costs_api,
            "_compute_license_governance_kpi",
            new=AsyncMock(return_value=license_metric),
        ),
        patch.object(
            costs_api,
            "get_settings",
            return_value=SimpleNamespace(ENCRYPTION_KEY="k", KDF_SALT="s"),
        ),
        patch.object(costs_api, "is_feature_enabled", side_effect=_feature_disabled_for_analytics),
    ):
        payload = await costs_api._compute_acceptance_kpis_payload(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            ingestion_window_hours=24,
            ingestion_target_success_rate_percent=95.0,
            recency_target_hours=48,
            chargeback_target_percent=90.0,
            max_unit_anomalies=0,
            current_user=user,
            db=db,  # type: ignore[arg-type]
        )

    by_key = {metric.key: metric for metric in payload.metrics}
    assert by_key["ingestion_reliability"].available is False
    assert by_key["chargeback_coverage"].available is False
    assert by_key["unit_economics_stability"].available is False


@pytest.mark.asyncio
async def test_get_costs_small_dataset_returns_dashboard_summary_directly() -> None:
    user = _user()
    db = _FakeDB()
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
            current_user=user,
        )

    assert out == expected
    assert response.status_code == 200
    mock_summary.assert_awaited_once_with(
        db,
        user.tenant_id,
        date(2026, 1, 1),
        date(2026, 1, 31),
        "aws",
    )


@pytest.mark.asyncio
async def test_get_canonical_quality_skips_alert_when_notify_flag_disabled() -> None:
    user = _user()
    db = _FakeDB()
    quality = {
        "target_percentage": 99.0,
        "total_records": 250,
        "mapped_percentage": 80.0,
        "unmapped_records": 50,
        "meets_target": False,
    }

    with (
        patch.object(
            costs_api.CostAggregator,
            "get_canonical_data_quality",
            new=AsyncMock(return_value=quality),
        ),
        patch.object(
            costs_api.NotificationDispatcher,
            "send_alert",
            new=AsyncMock(),
        ) as mock_alert,
    ):
        out = await costs_api.get_canonical_quality(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            notify_on_breach=False,
            db=db,  # type: ignore[arg-type]
            current_user=user,
        )

    assert out == quality
    mock_alert.assert_not_awaited()
    assert "alert_triggered" not in out


@pytest.mark.asyncio
async def test_get_cost_anomalies_skips_dispatch_when_alert_disabled() -> None:
    user = _user()
    db = _FakeDB()
    anomaly = SimpleNamespace()
    service = SimpleNamespace(detect=AsyncMock(return_value=[anomaly]))

    with (
        patch.object(costs_api, "CostAnomalyDetectionService", return_value=service),
        patch.object(
            costs_api,
            "dispatch_cost_anomaly_alerts",
            new=AsyncMock(return_value=1),
        ) as mock_dispatch,
        patch.object(
            costs_api,
            "_anomaly_to_response_item",
            return_value=costs_api.CostAnomalyItem(
                day="2026-01-31",
                provider="aws",
                account_id="123456789012",
                account_name="prod",
                service="ec2",
                actual_cost_usd=100.0,
                expected_cost_usd=10.0,
                delta_cost_usd=90.0,
                percent_change=900.0,
                kind="spike",
                probable_cause="Burst workload",
                confidence=0.95,
                severity="high",
            ),
        ),
    ):
        response = await costs_api.get_cost_anomalies(
            target_date=date(2026, 1, 31),
            lookback_days=28,
            provider="aws",
            min_abs_usd=25.0,
            min_percent=30.0,
            min_severity="medium",
            alert=False,
            suppression_hours=24,
            user=user,
            db=db,  # type: ignore[arg-type]
        )

    assert response.count == 1
    assert response.alerted_count == 0
    mock_dispatch.assert_not_awaited()
    service.detect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unit_economics_skips_alert_when_flag_disabled_with_anomaly() -> None:
    user = _user()
    db = _FakeDB()
    settings_row = SimpleNamespace(
        id=uuid4(),
        default_request_volume=1000.0,
        default_workload_volume=100.0,
        default_customer_volume=20.0,
        anomaly_threshold_percent=15.0,
    )
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

    with (
        patch.object(
            costs_api,
            "_get_or_create_unit_settings",
            new=AsyncMock(return_value=settings_row),
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
            new=AsyncMock(),
        ) as mock_alert,
    ):
        response = await costs_api.get_unit_economics(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider=None,
            request_volume=None,
            workload_volume=None,
            customer_volume=None,
            alert_on_anomaly=False,
            user=user,
            db=db,  # type: ignore[arg-type]
        )

    assert response.anomaly_count == 1
    assert response.alert_dispatched is False
    mock_alert.assert_not_awaited()
