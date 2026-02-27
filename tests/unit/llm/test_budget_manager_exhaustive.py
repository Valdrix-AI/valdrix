import pytest
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.llm.budget_manager import LLMBudgetManager, BudgetStatus
from app.shared.core.exceptions import BudgetExceededError
from app.models.llm import LLMBudget
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    LLMBudgetManager._local_global_abuse_block_until = None
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
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
    budget.monthly_spend_usd = Decimal("0.0")
    budget.pending_reservations_usd = Decimal("0.0")
    budget.budget_reset_at = datetime.now(timezone.utc)
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    mock_db.execute.return_value = res

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
            tenant_id, mock_db, model="gpt-4o"
        )
    assert cost == Decimal("0.0062")


@pytest.mark.asyncio
async def test_record_usage(mock_db, tenant_id):
    budget = MagicMock(
        monthly_spend_usd=Decimal("0.0"),
        pending_reservations_usd=Decimal("0.0"),
    )
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    mock_db.execute.return_value = res

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            return_value=PricingTier.FREE,
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
    budget.monthly_spend_usd = Decimal("1.0")
    budget.pending_reservations_usd = Decimal("0.0")
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    mock_db.execute.return_value = res

    with patch("app.shared.llm.budget_manager.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        status = await LLMBudgetManager.check_budget(tenant_id, mock_db)
        assert status == BudgetStatus.OK


@pytest.mark.asyncio
async def test_budget_exceeded_error_details(mock_db, tenant_id):
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=1.0)
    budget.hard_limit = True
    budget.monthly_spend_usd = Decimal("2.0")
    budget.pending_reservations_usd = Decimal("0.0")
    res = MagicMock()
    res.scalar_one_or_none.return_value = budget
    mock_db.execute.return_value = res

    with patch("app.shared.llm.budget_manager.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        with pytest.raises(BudgetExceededError) as exc:
            await LLMBudgetManager.check_budget(tenant_id, mock_db)
        assert "exceeded" in str(exc.value)


def test_to_decimal_none_and_invalid_paths() -> None:
    assert LLMBudgetManager._to_decimal(None) == Decimal("0")

    with patch("app.shared.llm.budget_manager.logger") as logger:
        assert LLMBudgetManager._to_decimal(object()) == Decimal("0")
        logger.warning.assert_called_once()


def test_estimate_cost_global_fallback_logs_warning() -> None:
    with patch("app.shared.llm.budget_manager.logger") as logger:
        cost = LLMBudgetManager.estimate_cost(
            prompt_tokens=1000,
            completion_tokens=1000,
            model="unknown-model",
            provider="unknown-provider",
        )

    assert cost == Decimal("0.0200")
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_fair_use_delegator_methods() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    start = datetime.now(timezone.utc)
    end = datetime.now(timezone.utc)

    with (
        patch(
            "app.shared.llm.budget_fair_use.enforce_daily_analysis_limit",
            new=AsyncMock(),
        ) as enforce_daily,
        patch(
            "app.shared.llm.budget_fair_use.fair_use_inflight_key",
            return_value="fair-use:tenant",
        ) as inflight_key,
        patch(
            "app.shared.llm.budget_fair_use.fair_use_tier_allowed",
            return_value=True,
        ) as tier_allowed,
        patch(
            "app.shared.llm.budget_fair_use.fair_use_daily_soft_cap",
            return_value=42,
        ) as daily_soft_cap,
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=7),
        ) as count_window,
        patch(
            "app.shared.llm.budget_fair_use.acquire_fair_use_inflight_slot",
            new=AsyncMock(return_value=(True, 1)),
        ) as acquire_slot,
        patch(
            "app.shared.llm.budget_fair_use.release_fair_use_inflight_slot",
            new=AsyncMock(),
        ) as release_slot,
        patch(
            "app.shared.llm.budget_fair_use.enforce_fair_use_guards",
            new=AsyncMock(return_value=False),
        ) as enforce_guards,
    ):
        await LLMBudgetManager._enforce_daily_analysis_limit(
            tenant_id,
            db,
            user_id=tenant_id,
            actor_type="user",
        )
        assert LLMBudgetManager._fair_use_inflight_key(tenant_id) == "fair-use:tenant"
        assert LLMBudgetManager._fair_use_tier_allowed(PricingTier.PRO) is True
        assert LLMBudgetManager._fair_use_daily_soft_cap(PricingTier.GROWTH) == 42
        assert (
            await LLMBudgetManager._count_requests_in_window(
                tenant_id=tenant_id,
                db=db,
                start=start,
                end=end,
            )
            == 7
        )
        assert (
            await LLMBudgetManager._acquire_fair_use_inflight_slot(
                tenant_id=tenant_id,
                max_inflight=2,
                ttl_seconds=60,
            )
            == (True, 1)
        )
        await LLMBudgetManager._release_fair_use_inflight_slot(tenant_id)
        assert (
            await LLMBudgetManager._enforce_fair_use_guards(
                tenant_id=tenant_id,
                db=db,
                tier=PricingTier.PRO,
            )
            is False
        )

    enforce_daily.assert_awaited_once()
    inflight_key.assert_called_once_with(tenant_id)
    tier_allowed.assert_called_once_with(PricingTier.PRO)
    daily_soft_cap.assert_called_once_with(PricingTier.GROWTH)
    count_window.assert_awaited_once()
    acquire_slot.assert_awaited_once()
    release_slot.assert_awaited_once()
    enforce_guards.assert_awaited_once()
