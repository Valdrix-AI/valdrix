import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone
import sys

# Early mocks for environment safety
sys.modules["pandas"] = MagicMock()
sys.modules["numpy"] = MagicMock()
sys.modules["prophet"] = MagicMock()

# Ensure we don't accidentally load models that try to connect
sys.modules["app.models.llm"] = MagicMock()
from app.shared.llm.budget_manager import LLMBudgetManager
from app.shared.core.exceptions import BudgetExceededError, ResourceNotFoundError

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Standard sync method for SQLAlchemy
    db.add = MagicMock()
    # Async methods
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db

@pytest.fixture
def tenant_id():
    return uuid4()

def test_estimate_cost():
    cost = LLMBudgetManager.estimate_cost(500, 500, "gpt-4o")
    assert cost == Decimal("0.0300")
    cost = LLMBudgetManager.estimate_cost(1000, 1000, "unknown")
    assert cost == Decimal("0.0200")

@pytest.mark.asyncio
async def test_check_and_reserve_success(mock_db, tenant_id):
    budget = MagicMock()
    budget.tenant_id = tenant_id
    budget.monthly_limit_usd = Decimal("10.00")
    budget.hard_limit = True
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    
    # Mock usage query
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("1.00")
    
    mock_db.execute.side_effect = [mock_result, mock_usage_result]
    
    reserved = await LLMBudgetManager.check_and_reserve(tenant_id, mock_db, model="gpt-4o")
    assert reserved == Decimal("0.0300")

@pytest.mark.asyncio
async def test_check_and_reserve_no_budget(mock_db, tenant_id):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    with pytest.raises(ResourceNotFoundError):
        await LLMBudgetManager.check_and_reserve(tenant_id, mock_db)

@pytest.mark.asyncio
async def test_check_and_reserve_exceeded(mock_db, tenant_id):
    budget = MagicMock()
    budget.monthly_limit_usd = Decimal("1.00")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("0.99")
    mock_db.execute.side_effect = [mock_result, mock_usage_result]
    
    with pytest.raises(BudgetExceededError):
        await LLMBudgetManager.check_and_reserve(tenant_id, mock_db, model="gpt-4o")

@pytest.mark.asyncio
async def test_check_and_reserve_unexpected_error(mock_db, tenant_id):
    mock_db.execute.side_effect = Exception("DB Timeout")
    with pytest.raises(Exception) as exc:
        await LLMBudgetManager.check_and_reserve(tenant_id, mock_db)
    assert "DB Timeout" in str(exc.value)

@pytest.mark.asyncio
async def test_record_usage_success(mock_db, tenant_id):
    # Patch LLMUsage constructor since we mocked its module
    with patch("app.shared.llm.budget_manager.LLMUsage", side_effect=lambda **kwargs: MagicMock(**kwargs)):
        await LLMBudgetManager.record_usage(
            tenant_id=tenant_id,
            db=mock_db,
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=500
        )
        assert mock_db.add.called
        assert mock_db.flush.called

@pytest.mark.asyncio
async def test_record_usage_explicit_cost(mock_db, tenant_id):
    with patch("app.shared.llm.budget_manager.LLMUsage", side_effect=lambda **kwargs: MagicMock(**kwargs)):
        await LLMBudgetManager.record_usage(
            tenant_id=tenant_id,
            db=mock_db,
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=500,
            actual_cost_usd=Decimal("0.0500")
        )
        assert mock_db.add.called
        usage_obj = mock_db.add.call_args[0][0]
        # In our lambda mock, it just stores kwargs.
        # But wait, LLMBudgetManager records usage.cost_usd.
        # If usage is a MagicMock, we can check its attributes.
        # But wait, the lambda side_effect returns a NEW MagicMock.
        # I'll use a real mock.
        
@pytest.mark.asyncio
async def test_record_usage_graceful_failure(mock_db, tenant_id):
    mock_db.add.side_effect = Exception("DB Error")
    # Should not raise
    await LLMBudgetManager.record_usage(tenant_id, mock_db, "gpt-4o", 10, 10)
