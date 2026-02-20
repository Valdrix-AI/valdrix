import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from app.shared.llm.budget_manager import LLMBudgetManager, BudgetStatus
from app.shared.core.exceptions import BudgetExceededError


@pytest.mark.asyncio
async def test_estimate_cost_standard():
    """Verify cost estimation for standard models."""
    # gpt-4o: input $2.5, output $10.0 per 1M tokens
    cost = LLMBudgetManager.estimate_cost(1000, 1000, "gpt-4o", "openai")
    # (1000 * 2.5 / 1M) + (1000 * 10.0 / 1M) = 0.0025 + 0.0100 = 0.0125
    assert cost == Decimal("0.0125")


@pytest.mark.asyncio
async def test_record_usage_byok_flat_fee():
    """Verify that BYOK requests incur no extra per-request surcharge."""
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = MagicMock()

    # Mock db.execute to return a valid-looking result for budget check
    # This prevents the exception that causes logger.error to be called
    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = Decimal("100.00")
    mock_budget.alert_threshold_percent = 80
    mock_budget.alert_sent_at = datetime.now(timezone.utc)
    mock_budget.monthly_spend_usd = Decimal("0.00")
    mock_budget.pending_reservations_usd = Decimal("0.00")

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_budget
    db.execute.return_value = exec_result

    tenant_id = uuid4()

    # Ensure logger is mocked to avoid coroutine warnings if it's somehow AsyncMock
    with patch("app.shared.llm.budget_manager.logger") as mock_logger:
        mock_logger.error = MagicMock()
        mock_logger.info = MagicMock()

        modal_tier = AsyncMock(return_value=MagicMock(value="pro"))
        with patch("app.shared.llm.budget_manager.get_tenant_tier", modal_tier):
            # Patch LLMUsage to avoid SQLAlchemy model loading issues
            with patch("app.shared.llm.budget_manager.LLMUsage") as MockUsage:
                await LLMBudgetManager.record_usage(
                    tenant_id=tenant_id,
                    db=db,
                    model="gpt-4",
                    prompt_tokens=1000,
                    completion_tokens=1000,
                    provider="openai",
                    is_byok=True,
                )

                # Verify usage creation
                MockUsage.assert_called_once()
                _, kwargs = MockUsage.call_args
                assert kwargs["cost_usd"] == Decimal("0.00")
                assert kwargs["is_byok"] is True

                # Verify db.add was called
                db.add.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_reserve_hard_limit():
    """Verify that exceeding hard limit raises BudgetExceededError."""
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    tenant_id = uuid4()

    # Mock budget with $5 limit and hard_limit enabled
    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = Decimal("5.00")
    mock_budget.hard_limit = True
    mock_budget.monthly_spend_usd = Decimal("4.99")
    mock_budget.pending_reservations_usd = Decimal("0.00")
    mock_budget.budget_reset_at = datetime.now(timezone.utc)

    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_budget)

    with (
        patch.object(
            LLMBudgetManager, "_enforce_daily_analysis_limit", new=AsyncMock()
        ),
        pytest.raises(BudgetExceededError) as exc,
    ):
        await LLMBudgetManager.check_and_reserve(
            tenant_id=tenant_id,
            db=db,
            model="gpt-4o",  # Costs $0.02 for 1k/1k
            prompt_tokens=1000,
            completion_tokens=1000,
        )
    assert "budget exceeded" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_budget_status_soft_limit():
    """Verify detection of soft limit thresholds."""
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    tenant_id = uuid4()

    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = Decimal("100.00")
    mock_budget.alert_threshold_percent = 80
    mock_budget.hard_limit = False
    mock_budget.monthly_spend_usd = Decimal("85.00")
    mock_budget.pending_reservations_usd = Decimal("0.00")

    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_budget)

    with patch("app.shared.llm.budget_manager.get_cache_service") as mock_cache:
        mock_cache.return_value.enabled = False
        status = await LLMBudgetManager.check_budget(tenant_id, db)
        assert status == BudgetStatus.SOFT_LIMIT


@pytest.mark.asyncio
async def test_budget_alert_logic():
    """Verify that Slack alerts are triggered exactly once per month."""
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    tenant_id = uuid4()

    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = Decimal("100.00")
    mock_budget.alert_threshold_percent = 80
    mock_budget.alert_sent_at = None  # Not sent yet

    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_budget),  # Budget fetch
        MagicMock(scalar=lambda: Decimal("81.00")),  # Current usage fetch
    ]

    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new_callable=AsyncMock,
    ) as mock_get_tenant_slack:
        mock_instance = AsyncMock()
        mock_get_tenant_slack.return_value = mock_instance

        await LLMBudgetManager._check_budget_and_alert(tenant_id, db, Decimal("1.00"))

        # Verify send_alert was called (message contains 'Usage')
        mock_instance.send_alert.assert_called_once()
        args, kwargs = mock_instance.send_alert.call_args
        assert "Usage" in kwargs["message"]
        assert kwargs["severity"] == "warning"
        assert mock_budget.alert_sent_at is not None
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()
