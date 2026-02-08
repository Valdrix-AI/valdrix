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

async def refresh_llm_pricing(db_session=None):
    """
    Refresh the global LLM_PRICING dictionary from the database.
    Falls back to static defaults if DB is empty or unavailable.
    """
    from sqlalchemy import select
    from app.models.pricing import LLMProviderPricing
    
    try:
        if db_session is None:
            # Avoid top-level import to prevent circularity
            from app.shared.db.base import async_session_maker
            async with async_session_maker() as session:
                stmt = select(LLMProviderPricing).where(LLMProviderPricing.is_active == True)
                result = await session.execute(stmt)
                pricing_records = result.scalars().all()
        else:
            stmt = select(LLMProviderPricing).where(LLMProviderPricing.is_active == True)
            result = await db_session.execute(stmt)
            pricing_records = result.scalars().all()

        if not pricing_records:
            return

        # Clear existing dynamic entries (keep default fallbacks if desired)
        # For safety, we only update/add what we find in the DB
        for record in pricing_records:
            provider = record.provider
            model = record.model
            
            if provider not in LLM_PRICING:
                LLM_PRICING[provider] = {}
                
            LLM_PRICING[provider][model] = ProviderCost(
                input=float(record.input_cost_per_million),
                output=float(record.output_cost_per_million),
                free_tier_tokens=int(record.free_tier_tokens)
            )
            
            # Update default if it's the first one or matches some logic
            if "default" not in LLM_PRICING[provider]:
                 LLM_PRICING[provider]["default"] = LLM_PRICING[provider][model]

    except Exception:
        # Silently fail and use static defaults to prevent app crash
        pass
