import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from app.shared.llm.budget_manager import LLMBudgetManager
from app.shared.core.exceptions import BudgetExceededError
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    LLMBudgetManager._local_global_abuse_block_until = None
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_check_and_reserve_hard_limit(mock_db):
    """Test hard blocking on budget exceed."""
    tenant_id = uuid4()

    budget_mock = MagicMock(
        monthly_limit_usd=100.0,
        hard_limit=True,
        monthly_spend_usd=Decimal("100.0"),
        pending_reservations_usd=Decimal("0.0"),
        budget_reset_at=datetime.now(timezone.utc),
    )

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = budget_mock
    mock_db.execute.return_value = res1

    settings = MagicMock(
        LLM_FAIR_USE_GUARDS_ENABLED=False,
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=False,
    )
    with (
        patch(
            "app.shared.llm.budget_manager.get_settings",
            return_value=settings,
        ),
        patch.object(
            LLMBudgetManager, "_enforce_daily_analysis_limit", new=AsyncMock()
        ),
        pytest.raises(BudgetExceededError),
    ):
        await LLMBudgetManager.check_and_reserve(
            tenant_id,
            mock_db,
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=1000,
        )


@pytest.mark.asyncio
async def test_check_and_reserve_success(mock_db):
    """Test successful reservation."""
    tenant_id = uuid4()

    budget_mock = MagicMock(
        monthly_limit_usd=100.0,
        hard_limit=True,
        monthly_spend_usd=Decimal("50.0"),
        pending_reservations_usd=Decimal("0.0"),
        budget_reset_at=datetime.now(timezone.utc),
    )

    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = budget_mock
    mock_db.execute.return_value = res1

    settings = MagicMock(
        LLM_FAIR_USE_GUARDS_ENABLED=False,
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=False,
    )
    with (
        patch(
            "app.shared.llm.budget_manager.get_settings",
            return_value=settings,
        ),
        patch.object(
            LLMBudgetManager, "_enforce_daily_analysis_limit", new=AsyncMock()
        ),
    ):
        cost = await LLMBudgetManager.check_and_reserve(
            tenant_id,
            mock_db,
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=1000,
        )

    assert cost > 0


@pytest.mark.asyncio
async def test_record_usage(mock_db):
    """Test usage recording and metric increment."""
    tenant_id = uuid4()

    budget_mock = MagicMock(
        monthly_spend_usd=Decimal("0.00"),
        pending_reservations_usd=Decimal("0.00"),
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = budget_mock
    mock_db.execute.return_value = execute_result

    with (
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager._check_budget_and_alert",
            new_callable=AsyncMock,
        ) as mock_alert,
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier", new_callable=AsyncMock
        ) as mock_tier,
    ):
        mock_tier.return_value = PricingTier.PRO

        await LLMBudgetManager.record_usage(
            tenant_id, mock_db, "gpt-4o", 100, 100, actual_cost_usd=Decimal("0.05")
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited()
        mock_alert.assert_awaited()
