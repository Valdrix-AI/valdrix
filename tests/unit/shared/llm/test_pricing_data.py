from app.shared.llm.pricing_data import ProviderCost, LLM_PRICING, PROVIDER_COSTS

class TestProviderCost:
    def test_provider_cost_initialization(self):
        """Test ProviderCost initializes correctly with attributes and dict access."""
        cost = ProviderCost(input=1.0, output=2.0, free_tier_tokens=100)
        
        # Test attributes
        assert cost.input == 1.0
        assert cost.output == 2.0
        assert cost.free_tier_tokens == 100
        
        # Test dict access
        assert cost["input"] == 1.0
        assert cost["output"] == 2.0
        assert cost["free_tier_tokens"] == 100

    def test_provider_cost_defaults(self):
        """Test ProviderCost default values."""
        cost = ProviderCost(input=1.0, output=2.0)
        assert cost.free_tier_tokens == 0
        assert cost["free_tier_tokens"] == 0

class TestLLMPricing:
    def test_pricing_structure(self):
        """Test LLM_PRICING has the expected structure."""
        required_providers = ["groq", "google", "openai", "anthropic"]
        for provider in required_providers:
            assert provider in LLM_PRICING
            assert isinstance(LLM_PRICING[provider], dict)
            assert "default" in LLM_PRICING[provider]

    def test_provider_costs_alias(self):
        """Test PROVIDER_COSTS is an alias for LLM_PRICING."""
        assert PROVIDER_COSTS is LLM_PRICING

    def test_pricing_values_are_provider_cost(self):
        """Test that pricing entries are instances of ProviderCost (or at least dicts)."""
        for provider_data in LLM_PRICING.values():
            for model_cost in provider_data.values():
                assert isinstance(model_cost, (ProviderCost, dict))
                assert "input" in model_cost
                assert "output" in model_cost
