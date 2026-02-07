import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.llm.hybrid_scheduler import HybridAnalysisScheduler, run_hybrid_analysis

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def scheduler(mock_db):
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service"), \
         patch("app.shared.llm.factory.LLMFactory.create"):
        return HybridAnalysisScheduler(mock_db)

class TestHybridSchedulerExhaustive:
    """Exhaustive tests for HybridAnalysisScheduler."""

    @pytest.mark.asyncio
    async def test_run_analysis_force_delta(self, scheduler):
        """Test forcing delta analysis (line 122)."""
        scheduler._run_delta_analysis = AsyncMock(return_value={"type": "delta"})
        res = await scheduler.run_analysis(uuid4(), [], force_delta=True)
        assert res["type"] == "delta"

    @pytest.mark.asyncio
    async def test_run_analysis_cache_hit_full_branch(self, scheduler):
        """Test reaching full analysis via should_run_full_analysis (line 124)."""
        scheduler.should_run_full_analysis = AsyncMock(return_value=True)
        scheduler._run_full_analysis = AsyncMock(return_value={"type": "full"})
        res = await scheduler.run_analysis(uuid4(), [])
        assert res["type"] == "full"

    @pytest.mark.asyncio
    async def test_run_analysis_delta_no_cache_merge(self, scheduler):
        """Test delta analysis without cached full result (line 151->154)."""
        scheduler.should_run_full_analysis = AsyncMock(return_value=False)
        scheduler._run_delta_analysis = AsyncMock(return_value={"type": "delta"})
        scheduler.cache.get = AsyncMock(return_value=None) # No cached full
        
        res = await scheduler.run_analysis(uuid4(), [])
        assert res["type"] == "delta"

    @pytest.mark.asyncio
    async def test_run_full_analysis_success(self, scheduler):
        """Test _run_full_analysis with valid JSON (lines 169-188)."""
        scheduler.analyzer.analyze = AsyncMock(return_value='{"summary": "ok"}')
        res = await scheduler._run_full_analysis(uuid4(), [])
        assert res["summary"] == "ok"
        assert res["analysis_type"] == "full_30_day"

    @pytest.mark.asyncio
    async def test_run_full_analysis_json_error(self, scheduler):
        """Test _run_full_analysis with invalid JSON (lines 181-182)."""
        scheduler.analyzer.analyze = AsyncMock(return_value='invalid json')
        res = await scheduler._run_full_analysis(uuid4(), [])
        assert res["raw_analysis"] == "invalid json"

    @pytest.mark.asyncio
    async def test_run_delta_analysis_no_sig_changes(self, scheduler):
        """Test _run_delta_analysis with no significant changes (lines 205-217)."""
        mock_delta = MagicMock()
        mock_delta.has_significant_changes = False
        mock_delta.days_compared = 3
        mock_delta.total_change = 0.5
        mock_delta.total_change_percent = 1.0
        
        scheduler.delta_service.compute_delta = AsyncMock(return_value=mock_delta)
        
        res = await scheduler._run_delta_analysis(uuid4(), [])
        assert res["status"] == "no_significant_changes"
        assert res["has_significant_changes"] is False

    @pytest.mark.asyncio
    async def test_run_delta_analysis_with_changes(self, scheduler):
        """Test _run_delta_analysis with significant changes (lines 220-238)."""
        mock_delta = MagicMock()
        mock_delta.has_significant_changes = True
        scheduler.delta_service.compute_delta = AsyncMock(return_value=mock_delta)
        
        with patch("app.shared.llm.hybrid_scheduler.analyze_with_delta", AsyncMock(return_value='{"summary": "delta ok"}')):
            res = await scheduler._run_delta_analysis(uuid4(), [])
            assert res["summary"] == "delta ok"
            assert res["analysis_type"] == "delta_3_day"

    @pytest.mark.asyncio
    async def test_run_delta_analysis_json_error(self, scheduler):
        """Test _run_delta_analysis with invalid JSON (lines 232-233)."""
        mock_delta = MagicMock()
        mock_delta.has_significant_changes = True
        scheduler.delta_service.compute_delta = AsyncMock(return_value=mock_delta)
        
        with patch("app.shared.llm.hybrid_scheduler.analyze_with_delta", AsyncMock(return_value='invalid')):
            res = await scheduler._run_delta_analysis(uuid4(), [])
            assert res["raw_analysis"] == "invalid"

    def test_merge_with_full_exhaustive(self, scheduler):
        """Test _merge_with_full logic (lines 248-263)."""
        delta = {"summary": "delta"}
        full = {
            "trends": ["trend1"],
            "seasonal_context": "summer",
            "analysis_date": "2023-01-01"
        }
        
        merged = scheduler._merge_with_full(delta, full)
        assert merged["trends"] == ["trend1"]
        assert merged["seasonal_context"] == "summer"
        assert merged["context_from"]["full_analysis_date"] == "2023-01-01"

    @pytest.mark.asyncio
    async def test_run_hybrid_analysis_wrapper(self, mock_db):
        """Test convenience wrapper (lines 281-282)."""
        with patch("app.shared.llm.hybrid_scheduler.HybridAnalysisScheduler") as mock_sched_cls:
            mock_sched = MagicMock()
            mock_sched.run_analysis = AsyncMock(return_value={"ok": True})
            mock_sched_cls.return_value = mock_sched
            
            res = await run_hybrid_analysis(mock_db, uuid4(), [])
            assert res["ok"] is True
