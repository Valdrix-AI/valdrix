import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.governance.domain.jobs.handlers.costs import (
    CostIngestionHandler,
    CostForecastHandler,
    CostExportHandler,
    CostAnomalyDetectionHandler,
)
from app.models.background_job import BackgroundJob


class _FatalTestSignal(BaseException):
    """Sentinel fatal error used to assert broad Exception handlers do not swallow BaseException."""


@pytest.mark.asyncio
async def test_ingestion_execute_missing_tenant_id(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=None)
    with pytest.raises(ValueError):
        await handler.execute(job, db)


@pytest.mark.asyncio
async def test_ingestion_execute_no_connections(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4())

    # Mock DB to return empty lists for AWS, Azure, GCP, SaaS, and license
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    )

    result = await handler.execute(job, db)
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_ingestion_execute_success(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})

    # Mock one AWS connection
    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.tenant_id = job.tenant_id
    conn.name = "AWS Test Connection"  # Explicitly set to string to avoid MagicMock being passed to DB

    db.execute = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.costs.list_tenant_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_factory,
        patch(
            "app.modules.reporting.domain.persistence.CostPersistenceService"
        ) as MockPersistence,
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine"
        ) as mock_engine_cls,
    ):
        adapter = mock_factory.return_value

        # Mock stream
        async def mock_stream(*args, **kwargs):
            yield {"cost_usd": 10.0}

        adapter.stream_cost_and_usage = mock_stream
        persistence = MockPersistence.return_value

        async def mock_save_records(records, **kwargs):
            async for _ in records:
                pass
            return {"records_saved": 1}

        persistence.save_records_stream = AsyncMock(side_effect=mock_save_records)
        mock_engine = AsyncMock()
        mock_engine.apply_rules_to_tenant.return_value = None
        mock_engine_cls.return_value = mock_engine

        result = await handler.execute(job, db)
        assert result["status"] == "completed"
        assert result["connections_processed"] == 1
        assert result["ingested"] == 1
        assert result["details"][0]["total_cost"] == 10.0


@pytest.mark.asyncio
async def test_forecast_execute_no_data(db):
    handler = CostForecastHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"start_date": "2023-01-01", "end_date": "2023-01-31"},
    )

    with patch(
        "app.modules.reporting.domain.aggregator.CostAggregator.get_summary"
    ) as mock_summary:
        mock_summary.return_value.records = []

        result = await handler.execute(job, db)
        assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_forecast_execute_success(db):
    handler = CostForecastHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"start_date": "2023-01-01", "end_date": "2023-01-31"},
    )

    with (
        patch(
            "app.modules.reporting.domain.aggregator.CostAggregator.get_summary"
        ) as mock_summary,
        patch(
            "app.shared.analysis.forecaster.SymbolicForecaster.forecast"
        ) as mock_forecast,
    ):
        mock_summary.return_value.records = [{"cost": 100}]
        mock_forecast.return_value = {"forecast": "data"}

        result = await handler.execute(job, db)
        assert result["status"] == "completed"
        assert result["forecast"] == {"forecast": "data"}


@pytest.mark.asyncio
async def test_export_execute_success(db):
    handler = CostExportHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"start_date": "2023-01-01", "end_date": "2023-01-31"},
    )

    with (
        patch(
            "app.modules.reporting.domain.aggregator.CostAggregator.get_cached_breakdown"
        ) as mock_breakdown,
        patch(
            "app.modules.reporting.domain.aggregator.CostAggregator.get_summary"
        ) as mock_summary,
    ):
        mock_breakdown.return_value = {}
        mock_summary.return_value.records = [1, 2, 3]
        mock_summary.return_value.total_cost = 150.0

        result = await handler.execute(job, db)
        assert result["status"] == "completed"
        assert result["records_exported"] == 3
        assert result["total_cost_usd"] == 150.0


@pytest.mark.asyncio
async def test_anomaly_detection_execute_no_matches(db):
    handler = CostAnomalyDetectionHandler()
    job = BackgroundJob(
        tenant_id=uuid4(), payload={"target_date": "2026-02-12", "alert": True}
    )

    with (
        patch(
            "app.shared.core.pricing.get_tenant_tier",
            new=AsyncMock(return_value=MagicMock(value="growth")),
        ),
        patch(
            "app.shared.core.pricing.is_feature_enabled",
            return_value=True,
        ),
        patch(
            "app.modules.reporting.domain.anomaly_detection.CostAnomalyDetectionService.detect",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.reporting.domain.anomaly_detection.dispatch_cost_anomaly_alerts",
            new=AsyncMock(return_value=0),
        ) as mock_dispatch,
    ):
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["count"] == 0
    assert result["alerted_count"] == 0
    assert mock_dispatch.await_count == 0


@pytest.mark.asyncio
async def test_anomaly_detection_execute_with_alerts(db):
    handler = CostAnomalyDetectionHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={
            "target_date": "2026-02-12",
            "provider": "aws",
            "min_severity": "medium",
            "alert": True,
            "suppression_hours": 6,
        },
    )

    mock_item = MagicMock()
    mock_item.day.isoformat.return_value = "2026-02-12"
    mock_item.provider = "aws"
    mock_item.account_id = uuid4()
    mock_item.account_name = "Prod"
    mock_item.service = "AmazonEC2"
    mock_item.actual_cost_usd = 250.0
    mock_item.expected_cost_usd = 100.0
    mock_item.delta_cost_usd = 150.0
    mock_item.percent_change = 150.0
    mock_item.kind = "spike"
    mock_item.probable_cause = "spend_spike"
    mock_item.confidence = 0.9
    mock_item.severity = "high"

    with (
        patch(
            "app.shared.core.pricing.get_tenant_tier",
            new=AsyncMock(return_value=MagicMock(value="growth")),
        ),
        patch(
            "app.shared.core.pricing.is_feature_enabled",
            return_value=True,
        ),
        patch(
            "app.modules.reporting.domain.anomaly_detection.CostAnomalyDetectionService.detect",
            new=AsyncMock(return_value=[mock_item]),
        ),
        patch(
            "app.modules.reporting.domain.anomaly_detection.dispatch_cost_anomaly_alerts",
            new=AsyncMock(return_value=1),
        ) as mock_dispatch,
    ):
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["count"] == 1
    assert result["alerted_count"] == 1
    assert result["provider"] == "aws"
    assert mock_dispatch.await_count == 1


@pytest.mark.asyncio
async def test_ingestion_execute_marks_connection_failed_on_recoverable_adapter_errors(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    db.execute = AsyncMock(return_value=None)
    db.add = MagicMock()

    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.tenant_id = job.tenant_id
    conn.name = "aws-conn"

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.costs.list_tenant_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            side_effect=RuntimeError("adapter unavailable"),
        ),
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine"
        ) as mock_engine_cls,
    ):
        mock_engine = AsyncMock()
        mock_engine.apply_rules_to_tenant.return_value = None
        mock_engine_cls.return_value = mock_engine
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["connections_processed"] == 1
    assert result["ingested"] == 0
    assert result["details"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_ingestion_execute_does_not_swallow_fatal_connection_errors(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    db.execute = AsyncMock(return_value=None)
    db.add = MagicMock()

    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.tenant_id = job.tenant_id
    conn.name = "aws-conn"

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.costs.list_tenant_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            side_effect=_FatalTestSignal(),
        ),
    ):
        with pytest.raises(_FatalTestSignal):
            await handler.execute(job, db)


@pytest.mark.asyncio
async def test_ingestion_execute_logs_and_continues_on_recoverable_attribution_errors(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    db.execute = AsyncMock(return_value=None)
    db.add = MagicMock()

    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.tenant_id = job.tenant_id
    conn.name = "aws-conn"

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.costs.list_tenant_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_factory,
        patch(
            "app.modules.reporting.domain.persistence.CostPersistenceService"
        ) as MockPersistence,
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine"
        ) as mock_engine_cls,
        patch("app.modules.governance.domain.jobs.handlers.costs.logger") as logger_mock,
    ):
        adapter = mock_factory.return_value

        async def mock_stream(*args, **kwargs):
            yield {"cost_usd": 12.0}

        adapter.stream_cost_and_usage = mock_stream
        persistence = MockPersistence.return_value

        async def consume(records, **kwargs):
            async for _ in records:
                pass
            return {"records_saved": 1}

        persistence.save_records_stream = AsyncMock(side_effect=consume)
        mock_engine = AsyncMock()
        mock_engine.apply_rules_to_tenant.side_effect = RuntimeError(
            "attribution unavailable"
        )
        mock_engine_cls.return_value = mock_engine

        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["connections_processed"] == 1
    logger_mock.error.assert_any_call(
        "attribution_trigger_failed",
        tenant_id=str(job.tenant_id),
        error="attribution unavailable",
    )


@pytest.mark.asyncio
async def test_ingestion_execute_does_not_swallow_fatal_attribution_errors(db):
    handler = CostIngestionHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    db.execute = AsyncMock(return_value=None)
    db.add = MagicMock()

    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.tenant_id = job.tenant_id
    conn.name = "aws-conn"

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.costs.list_tenant_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_factory,
        patch(
            "app.modules.reporting.domain.persistence.CostPersistenceService"
        ) as MockPersistence,
        patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine"
        ) as mock_engine_cls,
    ):
        adapter = mock_factory.return_value

        async def mock_stream(*args, **kwargs):
            yield {"cost_usd": 12.0}

        adapter.stream_cost_and_usage = mock_stream
        persistence = MockPersistence.return_value

        async def consume(records, **kwargs):
            async for _ in records:
                pass
            return {"records_saved": 1}

        persistence.save_records_stream = AsyncMock(side_effect=consume)
        mock_engine = AsyncMock()
        mock_engine.apply_rules_to_tenant.side_effect = _FatalTestSignal()
        mock_engine_cls.return_value = mock_engine

        with pytest.raises(_FatalTestSignal):
            await handler.execute(job, db)
