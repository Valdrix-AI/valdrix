import pytest
import uuid
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date
from app.shared.llm.hybrid_scheduler import HybridAnalysisScheduler


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get.return_value = None
    return cache


@pytest.fixture
def mock_analyzer():
    analyzer = MagicMock()
    analyzer.analyze = AsyncMock()
    return analyzer


@pytest.fixture
def mock_delta_service():
    service = MagicMock()
    service.compute_delta = AsyncMock()
    return service


@pytest.fixture
def scheduler(mock_db, mock_cache, mock_analyzer, mock_delta_service):
    with (
        patch(
            "app.shared.llm.hybrid_scheduler.get_cache_service", return_value=mock_cache
        ),
        patch(
            "app.shared.llm.hybrid_scheduler.DeltaAnalysisService",
            return_value=mock_delta_service,
        ),
        patch("app.shared.llm.factory.LLMFactory.create"),
        patch("app.shared.core.config.get_settings"),
        patch(
            "app.shared.llm.hybrid_scheduler.FinOpsAnalyzer", return_value=mock_analyzer
        ),
    ):
        scheduler = HybridAnalysisScheduler(mock_db)
        return scheduler


@pytest.mark.asyncio
async def test_should_run_full_analysis_sunday(scheduler):
    """Test fully analysis trigger on Sunday."""
    tenant_id = uuid.uuid4()

    # Mock Sunday (weekday = 6)
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        mock_date.today.return_value = date(2023, 10, 1)  # Oct 1 2023 is Sunday
        assert mock_date.today.return_value.weekday() == 6

        assert await scheduler.should_run_full_analysis(tenant_id) is True


@pytest.mark.asyncio
async def test_should_run_full_analysis_first_of_month(scheduler):
    """Test full analysis trigger on 1st of month."""
    tenant_id = uuid.uuid4()

    # Mock 1st of month, not Sunday (e.g. Wed Nov 1 2023)
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        mock_date.today.return_value = date(2023, 11, 1)
        assert mock_date.today.return_value.day == 1

        assert await scheduler.should_run_full_analysis(tenant_id) is True


@pytest.mark.asyncio
async def test_should_run_full_analysis_no_cache(scheduler):
    """Test full analysis trigger when no cache exists."""
    tenant_id = uuid.uuid4()

    # Mock normal day
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        mock_date.today.return_value = date(2023, 10, 4)  # Wed

        # Cache miss
        scheduler.cache.get.return_value = None

        assert await scheduler.should_run_full_analysis(tenant_id) is True


@pytest.mark.asyncio
async def test_run_analysis_full_flow(scheduler):
    """Test full analysis execution flow."""
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    analyzer = scheduler._get_analyzer()
    # Mock analyzer result
    analyzer.analyze.return_value = json.dumps(
        {"trends": ["up"], "savings": 100}
    )

    result = await scheduler.run_analysis(tenant_id, costs, force_full=True)

    assert result["analysis_type"] == "full_30_day"
    assert result["trends"] == ["up"]
    analyzer.analyze.assert_called_once()
    scheduler.cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_run_analysis_delta_flow(scheduler):
    """Test delta analysis execution flow."""
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    # Mock delta result - significant changes
    mock_delta = MagicMock()
    mock_delta.has_significant_changes = True
    scheduler.delta_service.compute_delta.return_value = mock_delta

    # Mock delta analysis via LLM (which is called via analyze_with_delta helper)
    with patch(
        "app.shared.llm.hybrid_scheduler.analyze_with_delta", new_callable=AsyncMock
    ) as mock_analyze_helper:
        mock_analyze_helper.return_value = json.dumps({"anomalies": ["spike"]})

        # Mock cached full analysis for merging
        scheduler.cache.get.return_value = {
            "trends": ["old_trend"],
            "analysis_date": "2023-01-01",
        }

        # Force delta
        result = await scheduler.run_analysis(tenant_id, costs, force_delta=True)

        assert result["analysis_type"] == "delta_3_day"
        assert result["anomalies"] == ["spike"]
        assert result["trends"] == ["old_trend"]  # Merged from cache
        assert result["has_significant_changes"] is True


@pytest.mark.asyncio
async def test_run_analysis_delta_no_changes(scheduler):
    """Test delta analysis with no significant changes."""
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    # Mock delta result - NO significant changes
    mock_delta = MagicMock()
    mock_delta.has_significant_changes = False
    mock_delta.days_compared = 3
    mock_delta.total_change = 0.0
    mock_delta.total_change_percent = 0.0
    scheduler.delta_service.compute_delta.return_value = mock_delta

    # Force delta
    result = await scheduler.run_analysis(tenant_id, costs, force_delta=True)

    assert result["analysis_type"] == "delta"


@pytest.mark.asyncio
async def test_should_run_full_analysis_false(scheduler):
    """Test full analysis returns False."""
    tenant_id = uuid.uuid4()

    # Mock normal day, cache hit
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        mock_date.today.return_value = date(2023, 10, 4)  # Wed

        # Cache hit
        scheduler.cache.get.return_value = "cached_analysis"

        assert await scheduler.should_run_full_analysis(tenant_id) is False


@pytest.mark.asyncio
async def test_run_analysis_automatic_full(scheduler):
    """Test automatic full analysis trigger."""
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    # Mock should_run_full_analysis to return True
    with patch.object(scheduler, "should_run_full_analysis", return_value=True):
        scheduler._get_analyzer().analyze.return_value = json.dumps({"trends": ["up"]})

        result = await scheduler.run_analysis(tenant_id, costs)

        assert result["analysis_type"] == "full_30_day"


@pytest.mark.asyncio
async def test_json_decode_error_handling(scheduler):
    """Test handling of malformed JSON from LLM."""
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    # Test Full Analysis JSON Error
    scheduler._get_analyzer().analyze.return_value = "Not JSON"
    result = await scheduler._run_full_analysis(tenant_id, costs)
    assert result["raw_analysis"] == "Not JSON"

    # Test Delta Analysis JSON Error
    mock_delta = MagicMock()
    mock_delta.has_significant_changes = True
    scheduler.delta_service.compute_delta.return_value = mock_delta

    with patch(
        "app.shared.llm.hybrid_scheduler.analyze_with_delta", new_callable=AsyncMock
    ) as mock_analyze:
        mock_analyze.return_value = "Not JSON"
        result = await scheduler._run_delta_analysis(tenant_id, costs)
        assert result["raw_analysis"] == "Not JSON"


@pytest.mark.asyncio
async def test_wrapper_function(mock_db):
    """Test the run_hybrid_analysis wrapper."""
    from app.shared.llm.hybrid_scheduler import run_hybrid_analysis

    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    # We need to patch HybridAnalysisScheduler to verify it's instantiated and called
    with patch(
        "app.shared.llm.hybrid_scheduler.HybridAnalysisScheduler"
    ) as MockScheduler:
        mock_instance = MockScheduler.return_value
        mock_instance.run_analysis = AsyncMock(return_value={"status": "ok"})

        result = await run_hybrid_analysis(mock_db, tenant_id, costs, force_full=True)

        assert result["status"] == "ok"
        MockScheduler.assert_called_once_with(mock_db)
        mock_instance.run_analysis.assert_called_once_with(
            tenant_id=tenant_id,
            current_costs=costs,
            previous_costs=None,
            force_full=True,
        )


@pytest.mark.asyncio
async def test_full_and_delta_analysis_handle_non_mapping_payloads(scheduler):
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    scheduler._get_analyzer().analyze.return_value = ["non-json-payload"]
    full_result = await scheduler._run_full_analysis(tenant_id, costs)
    assert full_result["raw_analysis"] == ["non-json-payload"]

    mock_delta = MagicMock()
    mock_delta.has_significant_changes = True
    scheduler.delta_service.compute_delta.return_value = mock_delta

    with patch(
        "app.shared.llm.hybrid_scheduler.analyze_with_delta",
        new_callable=AsyncMock,
        return_value=1234,
    ):
        delta_result = await scheduler._run_delta_analysis(tenant_id, costs)

    assert delta_result["raw_analysis"] == 1234
    assert delta_result["analysis_type"] == "delta_3_day"


def test_coerce_usage_summary_handles_invalid_rows_and_empty_fallback() -> None:
    tenant_id = uuid.uuid4()

    summary_with_invalid_row = HybridAnalysisScheduler._coerce_usage_summary(
        tenant_id=tenant_id,
        costs=[
            {
                "amount": object(),
                "date": "invalid-date",
                "service": "EC2",
                "region": "us-east-1",
            }
        ],
    )
    assert summary_with_invalid_row.total_cost == 0
    assert summary_with_invalid_row.records[0].amount == 0

    summary_empty = HybridAnalysisScheduler._coerce_usage_summary(
        tenant_id=tenant_id,
        costs=["not-a-dict"],
    )
    assert summary_empty.total_cost == 0
    assert len(summary_empty.records) == 1
    assert summary_empty.records[0].service == "Unknown"
    assert summary_empty.records[0].usage_type == "Unknown"


def test_merge_with_full_preserves_existing_delta_context(scheduler) -> None:
    merged = scheduler._merge_with_full(
        delta_result={
            "trends": ["current"],
            "seasonal_context": "already-present",
        },
        full_result={
            "trends": ["historical"],
            "seasonal_context": "historical-context",
            "analysis_date": "2026-02-27",
        },
    )

    assert merged["trends"] == ["current"]
    assert merged["seasonal_context"] == "already-present"
    assert merged["context_from"]["full_analysis_date"] == "2026-02-27"


def test_set_analyzer_allows_manual_injection(scheduler) -> None:
    injected = MagicMock()
    scheduler.set_analyzer(injected)
    assert scheduler._get_analyzer() is injected


@pytest.mark.asyncio
async def test_run_analysis_auto_delta_when_schedule_says_no(scheduler) -> None:
    tenant_id = uuid.uuid4()
    costs = [{"cost": 100}]

    with patch.object(scheduler, "should_run_full_analysis", return_value=False):
        with patch.object(
            scheduler, "_run_delta_analysis", new_callable=AsyncMock
        ) as mock_run_delta:
            mock_run_delta.return_value = {"analysis_type": "delta_3_day"}
            scheduler.cache.get.return_value = None

            result = await scheduler.run_analysis(tenant_id, costs)

    assert result["analysis_type"] == "delta_3_day"
    mock_run_delta.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_and_delta_analysis_accept_dict_payloads(scheduler) -> None:
    tenant_id = uuid.uuid4()
    costs = [{"cost": 1}]

    scheduler._get_analyzer().analyze.return_value = {"summary": "dict-result"}
    full_result = await scheduler._run_full_analysis(tenant_id, costs)
    assert full_result["summary"] == "dict-result"
    assert full_result["analysis_type"] == "full_30_day"

    mock_delta = MagicMock()
    mock_delta.has_significant_changes = True
    scheduler.delta_service.compute_delta.return_value = mock_delta
    with patch(
        "app.shared.llm.hybrid_scheduler.analyze_with_delta",
        new_callable=AsyncMock,
        return_value={"summary": "delta-dict"},
    ):
        delta_result = await scheduler._run_delta_analysis(tenant_id, costs)

    assert delta_result["summary"] == "delta-dict"
    assert delta_result["analysis_type"] == "delta_3_day"
