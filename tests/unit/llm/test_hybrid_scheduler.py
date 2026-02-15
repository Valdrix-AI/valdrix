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
        mock_cache.get.return_value = None  # No cache -> run full

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
        mock_cache.get.return_value = {"trends": []}  # For merge

        scheduler = HybridAnalysisScheduler(AsyncMock())
        scheduler._run_full_analysis = AsyncMock(return_value={"type": "full"})
        scheduler._run_delta_analysis = AsyncMock(return_value={"type": "delta"})
        scheduler._merge_with_full = MagicMock(return_value={"type": "merged"})

        # Force full
        with patch("app.shared.llm.factory.LLMFactory.create") as mock_create:
            mock_create.return_value = MagicMock()
            res = await scheduler.run_analysis(uuid4(), [], force_full=True)
            assert res["type"] == "full"

            # Delta (default if cached present and not Sunday)
            with patch.object(
                scheduler, "should_run_full_analysis", AsyncMock(return_value=False)
            ):
                res = await scheduler.run_analysis(uuid4(), [])
                assert res["type"] == "merged"


@pytest.mark.asyncio
async def test_run_delta_analysis_happy_path_with_mocked_provider():
    """Delta analysis should include orchestration metadata on successful provider analysis."""
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service") as mock_get_cache:
        mock_cache = AsyncMock()
        mock_get_cache.return_value = mock_cache

        scheduler = HybridAnalysisScheduler(AsyncMock())
        scheduler.analyzer = MagicMock()

        delta = MagicMock()
        delta.has_significant_changes = True
        delta.days_compared = 3
        delta.total_change = 12.5
        delta.total_change_percent = 8.4
        scheduler.delta_service.compute_delta = AsyncMock(return_value=delta)

        with patch(
            "app.shared.llm.hybrid_scheduler.analyze_with_delta",
            new=AsyncMock(return_value={"summary": "ok"}),
        ):
            result = await scheduler._run_delta_analysis(
                uuid4(), current_costs=[{"cost": 10}], previous_costs=[{"cost": 5}]
            )

        assert result["analysis_type"] == "delta_3_day"
        assert result["has_significant_changes"] is True
        assert result["summary"] == "ok"


@pytest.mark.asyncio
async def test_run_delta_analysis_provider_timeout_failure():
    """Provider timeout/failure path should propagate to caller for job retry handling."""
    with patch("app.shared.llm.hybrid_scheduler.get_cache_service") as mock_get_cache:
        mock_cache = AsyncMock()
        mock_get_cache.return_value = mock_cache

        scheduler = HybridAnalysisScheduler(AsyncMock())
        scheduler.analyzer = MagicMock()

        delta = MagicMock()
        delta.has_significant_changes = True
        delta.days_compared = 3
        delta.total_change = 99.0
        delta.total_change_percent = 45.0
        scheduler.delta_service.compute_delta = AsyncMock(return_value=delta)

        with patch(
            "app.shared.llm.hybrid_scheduler.analyze_with_delta",
            new=AsyncMock(side_effect=TimeoutError("provider timeout")),
        ):
            with pytest.raises(TimeoutError, match="provider timeout"):
                await scheduler._run_delta_analysis(
                    uuid4(),
                    current_costs=[{"cost": 100}],
                    previous_costs=[{"cost": 1}],
                )
