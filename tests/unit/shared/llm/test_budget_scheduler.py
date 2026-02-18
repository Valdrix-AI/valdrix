import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.shared.llm.budget_manager import LLMBudgetManager, BudgetStatus
from app.shared.llm.hybrid_scheduler import HybridAnalysisScheduler
from app.models.llm import LLMBudget, LLMUsage
from app.shared.core.exceptions import BudgetExceededError
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Explicitly configure execute to be AsyncMock returning a MagicMock result
    mock_result = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)
    
    def add_side_effect(obj):
        if hasattr(obj, 'budget_reset_at') and obj.budget_reset_at is None:
            obj.budget_reset_at = datetime.now(timezone.utc)
        if hasattr(obj, 'monthly_spend_usd') and obj.monthly_spend_usd is None:
            obj.monthly_spend_usd = Decimal("0.0")
        if hasattr(obj, 'pending_reservations_usd') and obj.pending_reservations_usd is None:
            obj.pending_reservations_usd = Decimal("0.0")
            
    db.add = MagicMock(side_effect=add_side_effect)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.mark.asyncio
class TestLLMBudgetManager:
    async def test_check_and_reserve_creates_budget_if_missing(self, mock_db, tenant_id):
        # Setup: No budget exists
        # mock_db.execute returns a mock_result (from fixture)
        # We set scalar_one_or_none on that result
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        # Mock get_tenant_tier
        with patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.PRO)), \
             patch.object(LLMBudgetManager, "_enforce_daily_analysis_limit", new=AsyncMock()):
                
            print("Calling check_and_reserve...")
            cost = await LLMBudgetManager.check_and_reserve(
                tenant_id, mock_db, model="gpt-4", prompt_tokens=100, completion_tokens=100
            )
            print(f"Cost returned: {cost}")

        # Verify budget created
        assert mock_db.add.called
        args = mock_db.add.call_args[0][0]
        assert isinstance(args, LLMBudget)
        assert args.tenant_id == tenant_id
        assert args.monthly_limit_usd == 50.0  # Pro tier default
        assert cost > 0

    async def test_check_and_reserve_enforces_hard_limit(self, mock_db, tenant_id):
        # Setup: Budget exists, almost full
        budget = LLMBudget(
            tenant_id=tenant_id,
            monthly_limit_usd=10.0,
            monthly_spend_usd=Decimal("9.99"),
            pending_reservations_usd=Decimal("0.0"),
            hard_limit=True,
            budget_reset_at=datetime.now(timezone.utc)
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = budget

        with patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.STARTER)), \
             patch.object(LLMBudgetManager, "_enforce_daily_analysis_limit", new=AsyncMock()):
                
            # Act & Assert
            # Increase tokens to ensure cost > 0.01 (remaining budget)
            with pytest.raises(BudgetExceededError) as exc:
                await LLMBudgetManager.check_and_reserve(
                    tenant_id, mock_db, model="gpt-4", prompt_tokens=100000, completion_tokens=100000
                )
            assert "exceeded" in str(exc.value)

    async def test_record_usage_decrements_reservation(self, mock_db, tenant_id):
        # Setup
        budget = LLMBudget(
            tenant_id=tenant_id,
            monthly_limit_usd=100.0,
            monthly_spend_usd=Decimal("10.0"),
            pending_reservations_usd=Decimal("5.0"),
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = budget
        
        # We assume estimate_cost returns 1.0. 
        # Since classmethod patching can be tricky, we can rely on the real calculation if we pass tokens that result in 1.0.
        # OR we patch it properly.
        mock_estimate = MagicMock(return_value=Decimal("1.0"))
        
        with patch.object(LLMBudgetManager, "estimate_cost", mock_estimate), \
             patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.PRO)):
            
            await LLMBudgetManager.record_usage(
                tenant_id, mock_db, model="gpt-4", prompt_tokens=1000, completion_tokens=1000, actual_cost_usd=Decimal("1.2")
            )

        # Assert
        # Pending should drop by reservation amount (1.0) -> 4.0
        assert budget.pending_reservations_usd == Decimal("4.0")
        # Spend should increase by actual amount (1.2) -> 11.2
        assert budget.monthly_spend_usd == Decimal("11.2")
        assert mock_db.add.called  # Usage record added

@pytest.mark.asyncio
class TestHybridAnalysisScheduler:
    async def test_should_run_full_analysis_sunday(self, mock_db, tenant_id):
        scheduler = HybridAnalysisScheduler(mock_db)
        
        # Mock date to be a Sunday
        with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
            mock_date.today.return_value.weekday.return_value = 6 # Sunday
            mock_date.today.return_value.day = 15
            
            should_run = await scheduler.should_run_full_analysis(tenant_id)
            assert should_run is True

    async def test_should_run_full_analysis_first_of_month(self, mock_db, tenant_id):
        scheduler = HybridAnalysisScheduler(mock_db)
        
        # Mock date to be Monday but 1st of month
        with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
            mock_date.today.return_value.weekday.return_value = 0 # Monday
            mock_date.today.return_value.day = 1
            
            should_run = await scheduler.should_run_full_analysis(tenant_id)
            assert should_run is True

    async def test_run_analysis_dispatches_delta(self, mock_db, tenant_id):
        scheduler = HybridAnalysisScheduler(mock_db)
        
        # Setup: Not Sunday, Not 1st, Cached full analysis exists
        scheduler.cache = MagicMock()
        scheduler.cache.get = AsyncMock(return_value={"some": "analysis"})
        
        with patch("app.shared.llm.hybrid_scheduler.date") as mock_date:
            mock_date.today.return_value.weekday.return_value = 0
            mock_date.today.return_value.day = 15
            
            # Mock internal methods
            scheduler._run_delta_analysis = AsyncMock(return_value={"analysis_type": "delta"})
            scheduler._merge_with_full = MagicMock(return_value={"merged": True})
            
            result = await scheduler.run_analysis(tenant_id, [{"cost": 10}])
            
            scheduler._run_delta_analysis.assert_awaited()
            assert result["merged"] is True

    async def test_run_analysis_forces_full(self, mock_db, tenant_id):
        scheduler = HybridAnalysisScheduler(mock_db)
        
        # Mock internal methods
        scheduler._run_full_analysis = AsyncMock(return_value={"analysis_type": "full"})
        scheduler.cache = MagicMock()
        scheduler.cache.set = AsyncMock()
        
        result = await scheduler.run_analysis(tenant_id, [{"cost": 10}], force_full=True)
        
        scheduler._run_full_analysis.assert_awaited()
        assert result["analysis_type"] == "full"
