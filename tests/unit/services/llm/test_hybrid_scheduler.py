import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
from uuid import uuid4
from app.shared.llm.hybrid_scheduler import HybridAnalysisScheduler, run_hybrid_analysis

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.enabled = True
    return cache

@pytest.fixture
def scheduler(mock_db, mock_cache):
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service", return_value=mock_cache):
        # Patch the original locations for in-function imports
        with patch("app.shared.llm.factory.LLMFactory") as mock_factory:
            with patch("app.shared.core.config.get_settings") as mock_settings:
                with patch("app.shared.llm.hybrid_scheduler.FinOpsAnalyzer"):
                    mock_factory.create.return_value = MagicMock()
                    mock_settings.return_value.LLM_PROVIDER = "groq"
                    return HybridAnalysisScheduler(mock_db)

@pytest.mark.asyncio
async def test_should_run_full_analysis_sunday(scheduler):
    """Test that full analysis is scheduled on Sundays."""
    # Mock date.today() to return a Sunday (2026-01-25 is a Sunday)
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        # Sunday = 6
        mock_date.today.return_value = date(2026, 1, 25)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        
        result = await scheduler.should_run_full_analysis(uuid4())
        assert result is True

@pytest.mark.asyncio
async def test_should_run_full_analysis_first_of_month(scheduler):
    """Test that full analysis is scheduled on the 1st of the month."""
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        # Monday Feb 1st
        mock_date.today.return_value = date(2026, 2, 1)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        
        result = await scheduler.should_run_full_analysis(uuid4())
        assert result is True

@pytest.mark.asyncio
async def test_should_run_full_analysis_no_cache(scheduler, mock_cache):
    """Test that full analysis is scheduled if no cache exists."""
    with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
        # Tuesday
        mock_date.today.return_value = date(2026, 1, 27)
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        
        mock_cache.get.return_value = None
        
        result = await scheduler.should_run_full_analysis(uuid4())
        assert result is True

@pytest.mark.asyncio
async def test_run_analysis_force_full(scheduler):
    """Test that run_analysis honors force_full."""
    tenant_id = uuid4()
    costs = [{"service": "EC2", "cost": 10}]
    
    with patch.object(scheduler, "_run_full_analysis", new_callable=AsyncMock) as mock_full:
        mock_full.return_value = {"type": "full"}
        
        result = await scheduler.run_analysis(tenant_id, costs, force_full=True)
        
        assert result["type"] == "full"
        mock_full.assert_called_once()

@pytest.mark.asyncio
async def test_run_analysis_delta_path(scheduler, mock_cache):
    """Test the delta analysis path with merging."""
    tenant_id = uuid4()
    costs = [{"service": "EC2", "cost": 10}]
    
    # Force delta by mocking should_run_full_analysis to False
    with patch.object(scheduler, "should_run_full_analysis", return_value=False):
        # Mock delta run
        with patch.object(scheduler, "_run_delta_analysis", new_callable=AsyncMock) as mock_delta:
            mock_delta.return_value = {"type": "delta", "insights": ["Spike"]}
            
            # Mock cached full analysis for merging
            mock_cache.get.return_value = {"type": "full", "trends": ["Seasonal"]}
            
            result = await scheduler.run_analysis(tenant_id, costs)
            
            assert result["type"] == "delta"
            assert "trends" in result
            assert result["trends"] == ["Seasonal"]
            assert "context_from" in result

@pytest.mark.asyncio
async def test_run_full_analysis_logic(scheduler):
    """Test internal _run_full_analysis logic."""
    tenant_id = uuid4()
    costs = [{"service": "EC2", "cost": 10}]
    
    with patch.object(scheduler.analyzer, "analyze", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = '{"insights": ["Full analysis"], "trends": []}'
        
        result = await scheduler._run_full_analysis(tenant_id, costs)
        
        assert result["insights"] == ["Full analysis"]
        assert result["analysis_type"] == "full_30_day"
        mock_analyze.assert_called_once()

@pytest.mark.asyncio
async def test_run_delta_analysis_insignificant(scheduler):
    """Test delta analysis when changes are small."""
    tenant_id = uuid4()
    costs = []
    
    with patch.object(scheduler.delta_service, "compute_delta", new_callable=AsyncMock) as mock_compute:
        mock_delta_obj = MagicMock()
        mock_delta_obj.has_significant_changes = False
        mock_delta_obj.total_change = 0.5
        mock_delta_obj.total_change_percent = 1.0
        mock_delta_obj.days_compared = 3
        mock_compute.return_value = mock_delta_obj
        
        result = await scheduler._run_delta_analysis(tenant_id, costs)
        
        assert result["status"] == "no_significant_changes"
        assert result["has_significant_changes"] is False

@pytest.mark.asyncio
async def test_run_delta_analysis_significant(scheduler):
    """Test delta analysis when changes are significant."""
    tenant_id = uuid4()
    costs = [{"service": "EC2", "cost": 20}]
    
    with patch.object(scheduler.delta_service, "compute_delta", new_callable=AsyncMock) as mock_compute:
        mock_delta_obj = MagicMock()
        mock_delta_obj.has_significant_changes = True
        mock_compute.return_value = mock_delta_obj
        
        with patch("app.shared.llm.hybrid_scheduler.analyze_with_delta", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = '{"insights": ["Delta analysis"], "has_significant_changes": true}'
            
            result = await scheduler._run_delta_analysis(tenant_id, costs)
            
            assert result["insights"] == ["Delta analysis"]
            assert result["analysis_type"] == "delta_3_day"
            assert result["has_significant_changes"] is True

def test_merge_with_full(scheduler):
    """Test merging delta result with full result context."""
    delta_result = {"insights": ["New Spike"]}
    full_result = {
        "analysis_date": "2024-01-01",
        "trends": ["Monthly Trend"],
        "seasonal_context": "Winter"
    }
    
    merged = scheduler._merge_with_full(delta_result, full_result)
    
    assert merged["insights"] == ["New Spike"]
    assert merged["trends"] == ["Monthly Trend"]
    assert merged["seasonal_context"] == "Winter"
    assert merged["context_from"]["full_analysis_date"] == "2024-01-01"

@pytest.mark.asyncio
async def test_run_full_analysis_json_error(scheduler):
    """Test _run_full_analysis handles JSON decode error."""
    tenant_id = uuid4()
    
    with patch.object(scheduler.analyzer, "analyze", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = "invalid json"
        
        result = await scheduler._run_full_analysis(tenant_id, [])
        
        assert "raw_analysis" in result
        assert result["raw_analysis"] == "invalid json"
        assert result["analysis_type"] == "full_30_day"

@pytest.mark.asyncio
async def test_convenience_wrapper(mock_db):
    """Test run_hybrid_analysis convenience wrapper."""
    with patch("app.shared.llm.hybrid_scheduler.HybridAnalysisScheduler.run_analysis", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"status": "ok"}
        
        result = await run_hybrid_analysis(mock_db, uuid4(), [])
        
        assert result["status"] == "ok"
        mock_run.assert_called_once()
