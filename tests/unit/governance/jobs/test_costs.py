import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from app.modules.governance.domain.jobs.handlers.costs import CostIngestionHandler, CostForecastHandler

@pytest.fixture
def mock_job():
    job = MagicMock()
    job.tenant_id = uuid4()
    job.payload = {}
    return job

@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    # Mock execute/scalars/all chain for querying connections
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    return session

@pytest.mark.asyncio
async def test_cost_ingestion_no_connections(mock_job, mock_db):
    """Test ingestion skips when no connections found."""
    handler = CostIngestionHandler()
    result = await handler.execute(mock_job, mock_db)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_active_connections"

@pytest.mark.asyncio
async def test_cost_ingestion_with_connection(mock_job, mock_db):
    """Test full ingestion flow for a connection."""
    handler = CostIngestionHandler()
    
    # Mock connection
    conn = MagicMock()
    conn.id = uuid4()
    conn.tenant_id = mock_job.tenant_id
    conn.provider = "aws"
    
    # Mock DB query to return connection
    result = MagicMock()
    result.scalars.return_value.all.side_effect = [[conn], [], [], [], []] # AWS, Azure, GCP, SaaS, License
    mock_db.execute.return_value = result
    
    # Mock Adapter and Persistence
    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_get_adapter, \
         patch("app.modules.reporting.domain.persistence.CostPersistenceService") as MockPersistence:
        
        adapter = mock_get_adapter.return_value
        # Mock async generator for stream
        async def mock_stream(*args, **kwargs):
            yield {"cost_usd": 10.0}
        adapter.stream_cost_and_usage = mock_stream
        
        persistence = MockPersistence.return_value
        
        async def consume_generator(records, **kwargs):
            async for _ in records:
                pass
            return {"records_saved": 1}
            
        persistence.save_records_stream.side_effect = consume_generator
        
        # Mock Attribution Engine (avoid import error or complex mocking)
        with patch.dict("sys.modules", {"app.modules.reporting.domain.attribution_engine": MagicMock()}):
            with patch("app.modules.reporting.domain.attribution_engine.AttributionEngine") as MockEngine:
                MockEngine.return_value.apply_rules_to_tenant = AsyncMock()
                
                res = await handler.execute(mock_job, mock_db)
                
                assert res["status"] == "completed"
                assert len(res["details"]) == 1
                assert res["details"][0]["total_cost"] == 10.0

@pytest.mark.asyncio
async def test_cost_forecast_handler(mock_job, mock_db):
    """Test forecasting job."""
    handler = CostForecastHandler()
    mock_job.payload = {
        "start_date": "2023-01-01",
        "end_date": "2023-01-31"
    }
    
    with patch("app.modules.reporting.domain.aggregator.CostAggregator.get_summary") as mock_summary, \
         patch("app.shared.analysis.forecaster.SymbolicForecaster.forecast") as mock_forecast:
        
        mock_summary.return_value = MagicMock(records=[1, 2, 3])
        mock_forecast.return_value = {"predicted": 100}
        
        res = await handler.execute(mock_job, mock_db)
        
        assert res["status"] == "completed"
        assert res["forecast"]["predicted"] == 100


@pytest.mark.asyncio
async def test_cost_ingestion_honors_backfill_window(mock_db):
    """Backfill payload window should be passed through to adapter stream calls."""
    job = MagicMock()
    job.tenant_id = uuid4()
    job.payload = {"start_date": "2026-01-01", "end_date": "2026-01-10"}
    handler = CostIngestionHandler()

    conn = MagicMock()
    conn.id = uuid4()
    conn.tenant_id = job.tenant_id
    conn.provider = "aws"
    conn.name = "AWS Backfill"

    result = MagicMock()
    result.scalars.return_value.all.side_effect = [[conn], [], [], [], []]
    mock_db.execute.return_value = result

    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter") as mock_get_adapter, \
         patch("app.modules.reporting.domain.persistence.CostPersistenceService") as MockPersistence, \
         patch("app.modules.reporting.domain.attribution_engine.AttributionEngine") as MockEngine:
        adapter = mock_get_adapter.return_value

        async def mock_stream(*args, **kwargs):
            yield {"cost_usd": 5.0}

        adapter.stream_cost_and_usage = AsyncMock(side_effect=mock_stream)
        persistence = MockPersistence.return_value

        async def consume(records, **kwargs):
            async for _ in records:
                pass
            return {"records_saved": 1}

        persistence.save_records_stream.side_effect = consume
        MockEngine.return_value.apply_rules_to_tenant = AsyncMock()

        res = await handler.execute(job, mock_db)

    assert res["status"] == "completed"
    assert res["window"]["backfill"] is True
    assert res["window"]["start_date"] == "2026-01-01"
    assert res["window"]["end_date"] == "2026-01-10"
    stream_kwargs = adapter.stream_cost_and_usage.await_args.kwargs
    assert stream_kwargs["start_date"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert stream_kwargs["end_date"] == datetime(2026, 1, 10, 23, 59, 59, 999999, tzinfo=timezone.utc)
