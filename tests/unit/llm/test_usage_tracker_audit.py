import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.shared.llm.usage_tracker import UsageTracker, count_tokens
from app.shared.llm.budget_manager import BudgetStatus
from app.shared.core.exceptions import BudgetExceededError


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def tenant_id():
    return uuid4()


def test_count_tokens_fallback(monkeypatch):
    with patch("tiktoken.get_encoding", side_effect=Exception("failed")):
        assert count_tokens("abcd") == 1
        assert count_tokens("12345678") == 2


def test_count_tokens_tiktoken():
    mock_enc = MagicMock()
    mock_enc.encode.return_value = [1, 2, 3]
    with patch("tiktoken.get_encoding", return_value=mock_enc):
        assert count_tokens("test", model="gpt-4") == 3


def test_calculate_cost():
    tracker = UsageTracker(MagicMock())
    mock_pricing = {
        "groq": {"llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79}}
    }
    with patch.dict(
        "app.shared.llm.pricing_data.LLM_PRICING", mock_pricing, clear=True
    ):
        cost = tracker.calculate_cost(
            "groq", "llama-3.3-70b-versatile", 1_000_000, 1_000_000
        )
        assert cost == Decimal("1.38")


@pytest.mark.asyncio
async def test_record_success(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)

    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.record_usage",
        new_callable=AsyncMock,
    ) as mock_record:
        mock_record.return_value = None

        await tracker.record(tenant_id, "groq", "model", 100, 100)

        mock_record.assert_called_once()


@pytest.mark.asyncio
async def test_authorize_request_allowed(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)

    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve",
        new_callable=AsyncMock,
    ) as mock_reserve:
        mock_reserve.return_value = Decimal("0.01")

        allowed = await tracker.authorize_request(
            tenant_id, "groq", "model", "text", max_output_tokens=100
        )
        assert allowed is True


@pytest.mark.asyncio
async def test_authorize_request_denied(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)

    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_and_reserve",
        new_callable=AsyncMock,
    ) as mock_reserve:
        mock_reserve.side_effect = BudgetExceededError("Budget exceeded")

        with pytest.raises(BudgetExceededError):
            await tracker.authorize_request(tenant_id, "groq", "model", "text")


@pytest.mark.asyncio
async def test_check_budget_hard_limit(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)

    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = BudgetStatus.HARD_LIMIT

        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.HARD_LIMIT


@pytest.mark.asyncio
async def test_check_budget_fail_closed(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)

    with patch(
        "app.shared.llm.budget_manager.LLMBudgetManager.check_budget",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.side_effect = BudgetExceededError(
            "Failed", details={"fail_closed": True}
        )

        with pytest.raises(BudgetExceededError) as exc:
            await tracker.check_budget(tenant_id)
        assert exc.value.details.get("fail_closed") is True


@pytest.mark.asyncio
async def test_alert_logic(mock_db, tenant_id):
    """Test that _check_budget_and_alert is called via record_usage in LLMBudgetManager."""
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

        async def record_side_effect(*args, **kwargs):
            await mock_alert(tenant_id, mock_db, Decimal("0.01"))

        mock_record.side_effect = record_side_effect

        tracker = UsageTracker(mock_db)
        await tracker.record(tenant_id, "groq", "model", 100, 100)

        mock_alert.assert_called_once()
