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

    # Calls:
    # 1. Select AWS
    # 2. Select Azure
    # 3. Select GCP
    # 4. Select SaaS
    # 5. Select License
    # 6. Select Platform
    # 7. Select Hybrid
    # 8. Upsert CloudAccount (pg_insert)

    mock_aws_res = MagicMock(scalars=lambda: MagicMock(all=lambda: [conn]))
    mock_empty_res = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

    db.execute = AsyncMock(
        side_effect=[
            mock_aws_res,
            mock_empty_res,
            mock_empty_res,
            mock_empty_res,
            mock_empty_res,
            mock_empty_res,
            mock_empty_res,
            None,
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    with (
        patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_factory,
        patch(
            "app.modules.reporting.domain.persistence.CostPersistenceService"
        ) as MockPersistence,
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
