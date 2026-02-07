import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import date
from app.shared.llm.hybrid_scheduler import HybridAnalysisScheduler

@pytest.mark.asyncio
async def test_should_run_full_analysis():
    """Test scheduling logic."""
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service") as mock_get_cache:
        mock_cache = AsyncMock()
        mock_get_cache.return_value = mock_cache
        
        scheduler = HybridAnalysisScheduler(AsyncMock())
        tenant_id = uuid4()
        
        # Mock Cache
        mock_cache.get.return_value = None # No cache -> run full
        
        # 1. First run (no cache)
        # Note: scheduler.cache is set to mock_cache
        assert await scheduler.should_run_full_analysis(tenant_id) is True
        
        # 2. Cached exists, Weekday (Not Sunday)
        mock_cache.get.return_value = {"data": "..."}
        with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
            # Mock Mon Jan 2nd 2023 (Monday, not 1st)
            mock_date.today.return_value = date(2023, 1, 2)
            assert await scheduler.should_run_full_analysis(tenant_id) is False
            
            # Mock Sun Jan 8th 2023 (Sunday)
            mock_date.today.return_value = date(2023, 1, 8)
            assert await scheduler.should_run_full_analysis(tenant_id) is True
            
            # Mock Jan 1st (Monthly)
            mock_date.today.return_value = date(2023, 2, 1)
            assert await scheduler.should_run_full_analysis(tenant_id) is True

@pytest.mark.asyncio
async def test_run_analysis_hybrid_flow():
    """Test dispatch to Delta vs Full."""
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service") as mock_get_cache:
        mock_cache = AsyncMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get.return_value = {"trends": []} # For merge
        
        scheduler = HybridAnalysisScheduler(AsyncMock())
        scheduler._run_full_analysis = AsyncMock(return_value={"type": "full"})
        scheduler._run_delta_analysis = AsyncMock(return_value={"type": "delta"})
        scheduler._merge_with_full = MagicMock(return_value={"type": "merged"})
        
        # Force full
        res = await scheduler.run_analysis(uuid4(), [], force_full=True)
        assert res["type"] == "full"
        
        # Delta (default if cached present and not Sunday)
        with patch.object(scheduler, "should_run_full_analysis", AsyncMock(return_value=False)):
            res = await scheduler.run_analysis(uuid4(), [])
            assert res["type"] == "merged"
