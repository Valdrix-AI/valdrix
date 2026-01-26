import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.shared.llm.usage_tracker import UsageTracker, BudgetStatus
from app.models.llm import LLMBudget
from uuid import uuid4
from decimal import Decimal
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture
def db_session():
    return AsyncMock()

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
    cost = tracker.calculate_cost("unknown", "model", 100, 100)
    assert cost == Decimal("0")

@pytest.mark.asyncio
async def test_authorize_request_within_budget(tracker, db_session):
    tenant_id = uuid4()
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=100.0, hard_limit=True)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = budget
    db_session.execute.return_value = mock_res
    
    with patch.object(tracker, "get_monthly_usage", return_value=Decimal("50.0")):
        # 1000 tokens for gpt-4o is very cheap
        res = await tracker.authorize_request(tenant_id, "openai", "gpt-4o", "hello", 1000)
        assert res is True

@pytest.mark.asyncio
async def test_authorize_request_exceeds_budget(tracker, db_session):
    tenant_id = uuid4()
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=10.0, hard_limit=True)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = budget
    db_session.execute.return_value = mock_res
    
    with patch.object(tracker, "get_monthly_usage", return_value=Decimal("9.99")):
        with pytest.raises(BudgetExceededError):
            # Requesting 1M tokens will definitely exceed the remaining $0.01
            await tracker.authorize_request(tenant_id, "anthropic", "claude-3-opus", "heavy payload", 1000000)

@pytest.mark.asyncio
async def test_check_budget_status_soft_limit(tracker, db_session):
    tenant_id = uuid4()
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=100.0, alert_threshold_percent=80)
    
    # Mock DB execute for check_budget
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = budget
    db_session.execute.return_value = mock_res
    
    # Mock monthly usage at 85%
    with patch.object(tracker, "get_monthly_usage", return_value=Decimal("85.0")):
        with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache:
            mock_cache.return_value.enabled = False
            status = await tracker.check_budget(tenant_id)
            assert status == BudgetStatus.SOFT_LIMIT

@pytest.mark.asyncio
async def test_check_budget_status_hard_limit_fail_closed(tracker, db_session):
    tenant_id = uuid4()
    # Mock DB failure
    db_session.execute.side_effect = Exception("DB Down")
    
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        with pytest.raises(BudgetExceededError) as exc:
            await tracker.check_budget(tenant_id)
        assert exc.value.details["fail_closed"] is True
