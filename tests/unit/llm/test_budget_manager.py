import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
import sys
from enum import Enum

# Standardize modules
from sqlalchemy import Column, String, Numeric, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class LLMBudget(Base):
    __tablename__ = "llm_budgets"
    id = Column(Numeric, primary_key=True)
    tenant_id = Column(String)
    monthly_limit_usd = Column(Numeric)
    hard_limit = Column(Boolean)
    alert_threshold_percent = Column(Numeric)
    alert_sent_at = Column(Numeric)

class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id = Column(Numeric, primary_key=True)
    tenant_id = Column(String)
    cost_usd = Column(Numeric)
    created_at = Column(Numeric)
    provider = Column(String)
    model = Column(String)
    input_tokens = Column(Numeric)
    output_tokens = Column(Numeric)
    total_tokens = Column(Numeric)
    operation_id = Column(String)
    request_type = Column(String)
    is_byok = Column(Boolean)

class mock_tier(Enum):
    FREE = "free"
    PRO = "pro"

# Mock ALL dependencies
with patch.dict(sys.modules, {
    "app.models.llm": MagicMock(
        LLMBudget=LLMBudget,
        LLMUsage=LLMUsage
    ),
    "app.shared.core.pricing": MagicMock(
        get_tenant_tier=AsyncMock(return_value=mock_tier.FREE)
    ),
    "app.shared.core.logging": MagicMock(
        audit_log=MagicMock()
    ),
    "app.shared.core.cache": MagicMock(
        get_cache_service=MagicMock(return_value=MagicMock(enabled=False))
    ),
    "app.shared.core.ops_metrics": MagicMock(
        LLM_PRE_AUTH_DENIALS=MagicMock(),
        LLM_SPEND_USD=MagicMock()
    ),
    "pandas": MagicMock(),
    "numpy": MagicMock(),
    "prophet": MagicMock()
}):
    from app.shared.llm.budget_manager import LLMBudgetManager
    from app.shared.core.exceptions import BudgetExceededError, ResourceNotFoundError

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db

@pytest.fixture
def tenant_id():
    return uuid4()

def test_estimate_cost():
    cost = LLMBudgetManager.estimate_cost(500, 500, "gpt-4o")
    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.0062")

@pytest.mark.asyncio
async def test_check_and_reserve_success(mock_db, tenant_id):
    budget = LLMBudget(
        tenant_id=tenant_id,
        monthly_limit_usd=Decimal("10.00"),
        hard_limit=True
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("1.00")
    mock_db.execute.side_effect = [mock_result, mock_usage_result]
    reserved = await LLMBudgetManager.check_and_reserve(tenant_id, mock_db, model="gpt-4o")
    assert reserved == Decimal("0.0062")

@pytest.mark.asyncio
async def test_check_and_reserve_no_budget(mock_db, tenant_id):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    with pytest.raises(ResourceNotFoundError):
        await LLMBudgetManager.check_and_reserve(tenant_id, mock_db)

@pytest.mark.asyncio
async def test_check_and_reserve_exceeded(mock_db, tenant_id):
    budget = LLMBudget(
        tenant_id=tenant_id,
        monthly_limit_usd=Decimal("0.01")
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("0.009")
    mock_db.execute.side_effect = [mock_result, mock_usage_result]
    with pytest.raises(BudgetExceededError):
        await LLMBudgetManager.check_and_reserve(tenant_id, mock_db, model="gpt-4o")

@pytest.mark.asyncio
async def test_record_usage_success(mock_db, tenant_id):
    # Mock result for _check_budget_and_alert
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=Decimal("10.00"), alert_threshold_percent=80, alert_sent_at=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("1.00")
    # record_usage does: 
    # 1. get_tenant_tier (mocked)
    # 2. _check_budget_and_alert: 
    #    - query budget
    #    - query sum usage
    mock_db.execute.side_effect = [mock_result, mock_usage_result]

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
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=Decimal("10.00"), alert_threshold_percent=80, alert_sent_at=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = budget
    mock_usage_result = MagicMock()
    mock_usage_result.scalar.return_value = Decimal("1.00")
    mock_db.execute.side_effect = [mock_result, mock_usage_result]

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
    assert usage_obj.cost_usd == Decimal("0.0500")

@pytest.mark.asyncio
async def test_record_usage_graceful_failure(mock_db, tenant_id):
    mock_db.add.side_effect = Exception("DB Error")
    # Should not raise
    await LLMBudgetManager.record_usage(tenant_id, mock_db, "gpt-4o", 10, 10)
