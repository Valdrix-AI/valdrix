from typing import Dict, Any

class ProviderCost(dict):
    """
    Provider cost metadata. 
    Inherits from dict for backward compatibility with legacy tests 
    and dictionary-style access pricing["input"].
    """
    def __init__(self, input: float, output: float, free_tier_tokens: int = 0):
        super().__init__(input=input, output=output, free_tier_tokens=free_tier_tokens)
        self.input = input
        self.output = output
        self.free_tier_tokens = free_tier_tokens

# LLM Provider costs (2026 pricing)
# Structured as: { provider: { model: ProviderCost } }
LLM_PRICING: Dict[str, Dict[str, Any]] = {
    "groq": {
        "llama-3.3-70b-versatile": ProviderCost(input=0.59, output=0.79, free_tier_tokens=14000),
        "mixtral-8x7b-32768": ProviderCost(input=0.27, output=0.27, free_tier_tokens=14000),
        "default": ProviderCost(input=0.59, output=0.79, free_tier_tokens=14000)
    },
    "google": {
        "gemini-2.0-flash": ProviderCost(input=0.25, output=0.5),
        "gemini-1.5-pro": ProviderCost(input=1.25, output=3.75),
        "default": ProviderCost(input=0.25, output=0.5)
    },
    "openai": {
        "gpt-4o": ProviderCost(input=2.5, output=10.0),
        "gpt-4o-mini": ProviderCost(input=0.15, output=0.6),
        "default": ProviderCost(input=0.15, output=0.6)
    },
    "anthropic": {
        "claude-3-7-sonnet": ProviderCost(input=3.0, output=15.0),
        "claude-3-5-sonnet": ProviderCost(input=3.0, output=15.0),
        "claude-3-opus": ProviderCost(input=15.0, output=75.0), # Added for testing
        "default": ProviderCost(input=3.0, output=15.0)
    }
}

# Alias for backward compatibility
PROVIDER_COSTS = LLM_PRICING
