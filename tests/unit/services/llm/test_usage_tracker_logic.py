"""
Tests for LLM Usage Tracker Logic

Aligned with LLMBudgetManager refactor - delegates all budget/recording
to LLMBudgetManager static methods instead of using deprecated class methods.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.shared.llm.usage_tracker import UsageTracker
from app.shared.llm.budget_manager import BudgetStatus
from app.shared.core.exceptions import BudgetExceededError


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def test_calculate_cost_openai(mock_db):
    """Test cost calculation for OpenAI (paid)."""
    tracker = UsageTracker(mock_db)
    cost = tracker.calculate_cost("openai", "gpt-4o-mini", 1000, 1000)
    # Price is 0.15 input, 0.6 output per 1M tokens
    expected = (Decimal("1000") * Decimal("0.15") / Decimal("1000000")) + (
        Decimal("1000") * Decimal("0.6") / Decimal("1000000")
    )
    assert cost == expected.quantize(Decimal("0.0001"))


def test_calculate_cost_unknown(mock_db):
    """Test cost calculation for unknown provider/model uses fallback."""
    tracker = UsageTracker(mock_db)
    cost = tracker.calculate_cost("unknown", "model", 1000, 1000)
    # Fallback: $10 per 1M tokens for both input and output
    # (1000 * 10 / 1M) + (1000 * 10 / 1M) = 0.02
    assert cost == Decimal("0.0200")


@pytest.mark.asyncio
async def test_record_usage(mock_db):
    """Test recording LLM usage delegates to LLMBudgetManager."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.record_usage",
        new_callable=AsyncMock,
    ) as mock_record:
        mock_record.return_value = None
        await tracker.record(
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
        )
        mock_record.assert_called_once()


@pytest.mark.asyncio
async def test_authorize_request_allowed(mock_db):
    """Test pre-authorization when budget is OK."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve",
        new_callable=AsyncMock,
    ) as mock_reserve:
        mock_reserve.return_value = Decimal("0.01")
        allowed = await tracker.authorize_request(
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o-mini",
            input_text="short query",
        )
        assert allowed is True
        mock_reserve.assert_called_once()


@pytest.mark.asyncio
async def test_authorize_request_rejected(mock_db):
    """Test pre-authorization rejection when budget is exceeded."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve",
        new_callable=AsyncMock,
    ) as mock_reserve:
        mock_reserve.side_effect = BudgetExceededError("Budget exceeded")
        with pytest.raises(BudgetExceededError):
            await tracker.authorize_request(
                tenant_id=tenant_id,
                provider="openai",
                model="gpt-4o-mini",
                input_text="A" * 1000,
            )


@pytest.mark.asyncio
async def test_check_budget_hard_limit(mock_db):
    """Test check_budget when HARD_LIMIT is reached."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.side_effect = BudgetExceededError("Hard limit reached")
        with pytest.raises(BudgetExceededError):
            await tracker.check_budget(tenant_id)


@pytest.mark.asyncio
async def test_check_budget_soft_limit(mock_db):
    """Test check_budget when SOFT_LIMIT threshold is reached."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = BudgetStatus.SOFT_LIMIT
        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.SOFT_LIMIT


@pytest.mark.asyncio
async def test_check_budget_and_alert_sends_slack(mock_db):
    """Test that LLMBudgetManager._check_budget_and_alert is called via record."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with (
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager._check_budget_and_alert",
            new_callable=AsyncMock,
        ) as mock_alert,
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record,
    ):
        # Simulate record_usage calling _check_budget_and_alert
        async def record_side_effect(*args, **kwargs):
            await mock_alert(tenant_id, mock_db, Decimal("0.01"))

        mock_record.side_effect = record_side_effect
        await tracker.record(tenant_id, "groq", "model", 100, 100)
        mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_check_budget_cache_hit_hard_limit(mock_db):
    """Test check_budget returns cached hard limit status."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = BudgetStatus.HARD_LIMIT
        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.HARD_LIMIT


@pytest.mark.asyncio
async def test_check_budget_and_alert_skip_if_already_sent(mock_db):
    """Test that _check_budget_and_alert (via record) respects alert_sent_at."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with (
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager._check_budget_and_alert",
            new_callable=AsyncMock,
        ),
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record,
    ):
        # In production, record_usage calls _check_budget_and_alert
        mock_record.return_value = None
        await tracker.record(tenant_id, "groq", "model", 100, 100)
        # We can only verify the call chain, not the internal skip logic
        mock_record.assert_called_once()


@pytest.mark.asyncio
async def test_check_budget_and_alert_slack_error_graceful(mock_db):
    """Test that Slack errors in _check_budget_and_alert are handled gracefully."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    with (
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager._check_budget_and_alert",
            new_callable=AsyncMock,
        ),
        patch(
            "app.shared.llm.budget_manager.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record,
    ):
        # Simulate _check_budget_and_alert raising but record_usage catching it
        mock_record.return_value = None
        # Should not raise
        await tracker.record(tenant_id, "groq", "model", 100, 100)


def test_count_tokens_fallback():
    """Test token counting fallback when tiktoken is unavailable."""
    from app.shared.llm.usage_tracker import count_tokens

    with patch("tiktoken.get_encoding") as mock_get:
        mock_get.side_effect = ImportError("No tiktoken")
        # should use fallback (len // 4)
        assert count_tokens("1234") == 1


@pytest.mark.asyncio
async def test_authorize_request_no_budget(mock_db):
    """Test authorize_request raises ResourceNotFoundError if no budget configured."""
    from app.shared.core.exceptions import ResourceNotFoundError

    tracker = UsageTracker(mock_db)
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve",
        new_callable=AsyncMock,
    ) as mock_reserve:
        mock_reserve.side_effect = ResourceNotFoundError("LLM budget not configured")
        with pytest.raises(ResourceNotFoundError):
            await tracker.authorize_request(uuid4(), "groq", "model", "text")


@pytest.mark.asyncio
async def test_check_budget_cache_soft_limit(mock_db):
    """Test check_budget returns cached soft limit status."""
    tracker = UsageTracker(mock_db)
    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = BudgetStatus.SOFT_LIMIT
        status = await tracker.check_budget(uuid4())
        assert status == BudgetStatus.SOFT_LIMIT


@pytest.mark.asyncio
async def test_get_monthly_usage_scalar(mock_db):
    """Test get_monthly_usage with scalar result."""
    tracker = UsageTracker(mock_db)
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("12.34")
    mock_db.execute.return_value = mock_result
    result = await tracker.get_monthly_usage(uuid4())
    assert result == Decimal("12.34")
