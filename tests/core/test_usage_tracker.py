"""
Tests for LLM Usage Tracker service.

Tests cover:
- Cost calculation for different models
- Monthly usage aggregation
- Budget threshold detection and alerting
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from uuid import uuid4
from app.shared.core.pricing import PricingTier
from app.shared.llm.usage_tracker import UsageTracker

from app.shared.llm.pricing_data import LLM_PRICING
# Import all models to prevent mapper errors during Mock usage


class TestCalculateCost:
    """Tests for calculate_cost method."""

    def test_groq_llama_cost_calculation(self):
        """Test cost calculation for Groq Llama model."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # 1000 input tokens, 500 output tokens
        cost = tracker.calculate_cost(
            provider="groq",
            model="llama-3.3-70b-versatile",
            input_tokens=1000,
            output_tokens=500,
        )

        # Expected: (1000 * 0.59 / 1M) + (500 * 0.79 / 1M) = 0.000985
        expected = Decimal("0.000985")
        assert abs(cost - expected) < Decimal("0.0001")

    def test_openai_gpt4o_cost_calculation(self):
        """Test cost calculation for OpenAI GPT-4o model."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        cost = tracker.calculate_cost(
            provider="openai", model="gpt-4o", input_tokens=1000, output_tokens=500
        )

        # Expected: (1000 * 2.50 / 1M) + (500 * 10.00 / 1M) = 0.0075
        expected = Decimal("0.0075")
        assert abs(cost - expected) < Decimal("0.0001")

    def test_anthropic_claude_cost_calculation(self):
        """Test cost calculation for Anthropic Claude model."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        cost = tracker.calculate_cost(
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
        )

        # Expected: (1000 * 3.00 / 1M) + (500 * 15.00 / 1M) = 0.0105
        expected = Decimal("0.0105")
        assert abs(cost - expected) < Decimal("0.0001")

    def test_unknown_model_returns_fallback_cost(self):
        """Test that unknown models return fallback cost instead of zero."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        cost = tracker.calculate_cost(
            provider="unknown_provider",
            model="unknown_model",
            input_tokens=1000,
            output_tokens=500,
        )

        # Expected (Fallback $10/1M): (1000 * 10 / 1M) + (500 * 10 / 1M) = 0.015
        assert cost == Decimal("0.0150")

    def test_known_provider_unknown_model_returns_provider_default(self):
        """Test that known provider with unknown model returns provider default."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        cost = tracker.calculate_cost(
            provider="openai",
            model="gpt-5-ultra-mega",  # Doesn't exist
            input_tokens=1000,
            output_tokens=500,
        )

        # Expected (OpenAI Default): (1000 * 0.15 / 1M) + (500 * 0.6 / 1M) = 0.00045 -> 0.0004
        assert cost == Decimal("0.0004")

    def test_zero_tokens_returns_zero(self):
        """Test that zero tokens returns zero cost."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        cost = tracker.calculate_cost(
            provider="groq",
            model="llama-3.3-70b-versatile",
            input_tokens=0,
            output_tokens=0,
        )

        assert cost == Decimal("0")


class TestLLMPricing:
    """Tests for LLM_PRICING configuration."""

    def test_all_providers_have_at_least_one_model(self):
        """Verify all providers have pricing configured."""
        required_providers = ["groq", "openai", "anthropic"]
        for provider in required_providers:
            assert provider in LLM_PRICING
            assert len(LLM_PRICING[provider]) > 0

    def test_all_models_have_input_output_pricing(self):
        """Verify all models have both input and output pricing."""
        for provider, models in LLM_PRICING.items():
            for model, pricing in models.items():
                assert "input" in pricing, f"{provider}/{model} missing input price"
                assert "output" in pricing, f"{provider}/{model} missing output price"
                assert pricing["input"] > 0, (
                    f"{provider}/{model} input price should be positive"
                )
                assert pricing["output"] > 0, (
                    f"{provider}/{model} output price should be positive"
                )


class TestRecordUsage:
    """Tests for record method (requires async mock)."""

    @pytest.mark.asyncio
    async def test_record_creates_usage_entry(self):
        """Test that record creates a usage entry in the database."""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()  # Ensure it's a mock we can assert on

        tracker = UsageTracker(mock_db)

        tenant_id = uuid4()

        # Mock the budget check to do nothing and get_tenant_tier to return a mock
        from app.shared.llm.budget_manager import LLMBudgetManager

        with (
            patch.object(
                LLMBudgetManager, "_check_budget_and_alert", new_callable=AsyncMock
            ),
            patch(
                "app.shared.llm.budget_manager.get_tenant_tier", new_callable=AsyncMock
            ) as mock_tier,
        ):
            mock_tier.return_value = PricingTier.PRO
            await tracker.record(
                tenant_id=tenant_id,
                provider="groq",
                model="llama-3.3-70b-versatile",
                input_tokens=1000,
                output_tokens=500,
                request_type="test",
            )

        # Verify db.add was called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()


class TestBudgetCheck:
    """Tests for budget threshold checking."""

    @pytest.mark.asyncio
    async def test_no_alert_when_no_budget_set(self):
        """Test no alert is sent when tenant has no budget."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = Decimal("0")
        mock_db.execute = AsyncMock(return_value=mock_result)

        tracker = UsageTracker(mock_db)
        tenant_id = uuid4()

        # Should not raise, should return silently
        await tracker._check_budget_and_alert(tenant_id)

    @pytest.mark.asyncio
    async def test_no_alert_under_threshold(self):
        """Test no alert when usage is under threshold."""
        mock_db = MagicMock()

        # Mock budget with 80% threshold, $10 limit
        mock_budget = MagicMock()
        mock_budget.monthly_limit_usd = Decimal("10.00")
        mock_budget.alert_threshold_percent = 80
        mock_budget.alert_sent_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget
        mock_result.scalar.return_value = Decimal("5.00")  # 50%
        mock_db.execute = AsyncMock(return_value=mock_result)

        tracker = UsageTracker(mock_db)

        # Mock get_monthly_usage to return $5 (50% of limit)
        with patch.object(
            tracker,
            "get_monthly_usage",
            new_callable=AsyncMock,
            return_value=Decimal("5.00"),
        ):
            # Should not alert since under threshold
            await tracker._check_budget_and_alert(uuid4())
