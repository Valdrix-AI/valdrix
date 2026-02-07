import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from uuid import uuid4
from app.shared.llm.budget_manager import LLMBudgetManager
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture
def mock_db():
    session = AsyncMock()
    return session

@pytest.mark.asyncio
async def test_check_and_reserve_hard_limit(mock_db):
    """Test hard blocking on budget exceed."""
    tenant_id = uuid4()
    
    # Mock DB Query: Budget Config
    budget_mock = MagicMock(monthly_limit_usd=100.0, hard_limit=True)
    
    # Mock DB Query: Current Usage
    usage_mock = Decimal("100.0") # Already hit limit
    
    # Setup chain of calls for execute().scalar_one_or_none() and execute().scalar()
    # 1. Budget Query
    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = budget_mock
    
    # 2. Usage Query
    res2 = MagicMock()
    res2.scalar.return_value = usage_mock
    
    mock_db.execute.side_effect = [res1, res2]
    
    with pytest.raises(BudgetExceededError):
        await LLMBudgetManager.check_and_reserve(
            tenant_id, mock_db, model="gpt-4o", prompt_tokens=1000, completion_tokens=1000
        )

@pytest.mark.asyncio
async def test_check_and_reserve_success(mock_db):
    """Test successful reservation."""
    tenant_id = uuid4()
    
    budget_mock = MagicMock(monthly_limit_usd=100.0, hard_limit=True)
    usage_mock = Decimal("50.0") # Well under limit
    
    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = budget_mock
    res2 = MagicMock()
    res2.scalar.return_value = usage_mock
    
    mock_db.execute.side_effect = [res1, res2]
    
    cost = await LLMBudgetManager.check_and_reserve(
        tenant_id, mock_db, model="gpt-4o", prompt_tokens=1000, completion_tokens=1000
    )
    
    assert cost > 0

@pytest.mark.asyncio
async def test_record_usage(mock_db):
    """Test usage recording and metric increment."""
    tenant_id = uuid4()
    
    with patch("app.shared.llm.budget_manager.LLMBudgetManager._check_budget_and_alert", new_callable=AsyncMock) as mock_alert, \
         patch("app.shared.llm.budget_manager.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        
        mock_tier.return_value = MagicMock(value="pro")
        
        await LLMBudgetManager.record_usage(
            tenant_id, mock_db, "gpt-4o", 100, 100, actual_cost_usd=Decimal("0.05")
        )
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited()
        mock_alert.assert_awaited()
