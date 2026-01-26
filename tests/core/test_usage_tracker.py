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
from app.shared.llm.usage_tracker import UsageTracker, LLM_PRICING


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
            output_tokens=500
        )
        
        # Expected: (1000 * 0.59 / 1M) + (500 * 0.79 / 1M) = 0.000985
        expected = Decimal("0.000985")
        assert abs(cost - expected) < Decimal("0.0001")
    
    def test_openai_gpt4o_cost_calculation(self):
        """Test cost calculation for OpenAI GPT-4o model."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)
        
        cost = tracker.calculate_cost(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500
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
            output_tokens=500
        )
        
        # Expected: (1000 * 3.00 / 1M) + (500 * 15.00 / 1M) = 0.0105
        expected = Decimal("0.0105")
        assert abs(cost - expected) < Decimal("0.0001")
    
    def test_unknown_model_returns_zero(self):
        """Test that unknown models return zero cost (graceful degradation)."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)
        
        cost = tracker.calculate_cost(
            provider="unknown_provider",
            model="unknown_model",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert cost == Decimal("0")
    
    def test_known_provider_unknown_model_returns_zero(self):
        """Test that known provider with unknown model returns zero."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)
        
        cost = tracker.calculate_cost(
            provider="openai",
            model="gpt-5-ultra-mega",  # Doesn't exist
            input_tokens=1000,
            output_tokens=500
        )
        
        assert cost == Decimal("0")
    
    def test_zero_tokens_returns_zero(self):
        """Test that zero tokens returns zero cost."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)
        
        cost = tracker.calculate_cost(
            provider="groq",
            model="llama-3.3-70b-versatile",
            input_tokens=0,
            output_tokens=0
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
                assert pricing["input"] > 0, f"{provider}/{model} input price should be positive"
                assert pricing["output"] > 0, f"{provider}/{model} output price should be positive"


class TestRecordUsage:
    """Tests for record method (requires async mock)."""
    
    @pytest.mark.asyncio
    async def test_record_creates_usage_entry(self):
        """Test that record creates a usage entry in the database."""
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        tracker = UsageTracker(mock_db)
        
        tenant_id = uuid4()
        
        # Mock the budget check to do nothing
        with patch.object(tracker, '_check_budget_and_alert', new_callable=AsyncMock):
            await tracker.record(
                tenant_id=tenant_id,
                provider="groq",
                model="llama-3.3-70b-versatile",
                input_tokens=1000,
                output_tokens=500,
                request_type="test"
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
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        tracker = UsageTracker(mock_db)
        
        # Mock get_monthly_usage to return $5 (50% of limit)
        with patch.object(tracker, 'get_monthly_usage', new_callable=AsyncMock, return_value=Decimal("5.00")):
            # Should not alert since under threshold
            await tracker._check_budget_and_alert(uuid4())
