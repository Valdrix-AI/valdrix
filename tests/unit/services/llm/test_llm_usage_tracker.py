import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.shared.llm.usage_tracker import UsageTracker
from app.shared.llm.budget_manager import BudgetStatus
from app.models.llm import LLMBudget
from uuid import uuid4
from decimal import Decimal
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture
def db_session():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db

@pytest.fixture
def tracker(db_session):
    return UsageTracker(db_session)

@pytest.mark.asyncio
async def test_calculate_cost(tracker):
    # openai gpt-4o-mini: input 0.15, output 0.6 per 1M
    cost = tracker.calculate_cost("openai", "gpt-4o-mini", 1000000, 1000000)
    assert cost == Decimal("0.75")

@pytest.mark.asyncio
async def test_calculate_cost_unknown_model(tracker):
    # Unknown models use fallback pricing ($10 per 1M tokens for both input/output)
    cost = tracker.calculate_cost("unknown", "model", 100, 100)
    # Fallback: (100 * 10 / 1M) + (100 * 10 / 1M) = 0.002
    assert cost == Decimal("0.0020")

@pytest.mark.asyncio
async def test_authorize_request_within_budget(tracker):
    tenant_id = uuid4()
    
    with patch("app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve", new_callable=AsyncMock) as mock_reserve:
        mock_reserve.return_value = Decimal("0.01")
        
        res = await tracker.authorize_request(tenant_id, "openai", "gpt-4o", "hello", 1000)
        assert res is True
        mock_reserve.assert_called_once()

@pytest.mark.asyncio
async def test_authorize_request_exceeds_budget(tracker):
    tenant_id = uuid4()
    
    with patch("app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve", new_callable=AsyncMock) as mock_reserve:
        mock_reserve.side_effect = BudgetExceededError("Budget exceeded")
        
        with pytest.raises(BudgetExceededError):
            await tracker.authorize_request(tenant_id, "anthropic", "claude-3-opus", "heavy payload", 1000000)

@pytest.mark.asyncio
async def test_check_budget_status_soft_limit(tracker):
    tenant_id = uuid4()
    
    with patch("app.shared.llm.budget_manager.LLMBudgetManager.check_budget", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = BudgetStatus.SOFT_LIMIT
        
        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.SOFT_LIMIT

@pytest.mark.asyncio
async def test_check_budget_status_hard_limit_fail_closed(tracker):
    tenant_id = uuid4()
    
    with patch("app.shared.llm.budget_manager.LLMBudgetManager.check_budget", new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = BudgetExceededError("DB Down", details={"fail_closed": True})
        
        with pytest.raises(BudgetExceededError) as exc:
            await tracker.check_budget(tenant_id)
        assert exc.value.details["fail_closed"] is True
