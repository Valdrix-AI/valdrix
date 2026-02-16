import pytest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.llm.budget_manager import LLMBudgetManager, BudgetStatus
from app.shared.core.exceptions import BudgetExceededError
from app.models.llm import LLMBudget


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def tenant_id():
    return uuid4()


def test_estimate_cost():
    cost = LLMBudgetManager.estimate_cost(1000, 500, "gpt-4o", "openai")
    assert cost == Decimal("0.0075")


@pytest.mark.asyncio
async def test_check_and_reserve(mock_db, tenant_id):
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=10.0)
    budget.hard_limit = True
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    res_usage = MagicMock()
    res_usage.scalar.return_value = Decimal("0")
    mock_db.execute.side_effect = [res, res_usage]

    cost = await LLMBudgetManager.check_and_reserve(tenant_id, mock_db, model="gpt-4o")
    assert cost == Decimal("0.0062")


@pytest.mark.asyncio
async def test_record_usage(mock_db, tenant_id):
    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            return_value=MagicMock(value="free"),
        ),
        patch.object(
            LLMBudgetManager, "_check_budget_and_alert", new_callable=AsyncMock
        ) as mock_alert,
    ):
        await LLMBudgetManager.record_usage(tenant_id, mock_db, "gpt-4o", 100, 100)
        assert mock_db.add.called
        assert mock_alert.called


@pytest.mark.asyncio
async def test_check_budget(mock_db, tenant_id):
    budget = LLMBudget(
        tenant_id=tenant_id, monthly_limit_usd=10.0, alert_threshold_percent=80
    )
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    res_usage = MagicMock()
    res_usage.scalar.return_value = Decimal("1.0")
    mock_db.execute.side_effect = [res, res_usage]

    with patch("app.shared.llm.budget_manager.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        status = await LLMBudgetManager.check_budget(tenant_id, mock_db)
        assert status == BudgetStatus.OK


@pytest.mark.asyncio
async def test_budget_exceeded_error_details(mock_db, tenant_id):
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=1.0)
    budget.hard_limit = True
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    res_usage = MagicMock()
    res_usage.scalar.return_value = Decimal("2.0")
    mock_db.execute.side_effect = [res, res_usage]

    with patch("app.shared.llm.budget_manager.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        with pytest.raises(BudgetExceededError) as exc:
            await LLMBudgetManager.check_budget(tenant_id, mock_db)
        assert "exceeded" in str(exc.value)
