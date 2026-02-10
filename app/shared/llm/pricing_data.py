from typing import Dict, Any, Optional
import structlog
import math

logger = structlog.get_logger()

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

# LLM Provider costs (static fallback; prefer DB-driven pricing refresh)
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

def _normalize_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None

def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed

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
            from app.shared.db.session import async_session_maker
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
            provider = _normalize_key(getattr(record, "provider", None))
            model = _normalize_key(getattr(record, "model", None))

            if not provider or not model:
                logger.warning(
                    "llm_pricing_record_missing_keys",
                    provider=provider,
                    model=model,
                )
                continue

            input_cost = _safe_float(getattr(record, "input_cost_per_million", None))
            output_cost = _safe_float(getattr(record, "output_cost_per_million", None))
            if input_cost is None or output_cost is None or input_cost < 0 or output_cost < 0:
                logger.warning(
                    "llm_pricing_record_invalid_cost",
                    provider=provider,
                    model=model,
                    input_cost=getattr(record, "input_cost_per_million", None),
                    output_cost=getattr(record, "output_cost_per_million", None),
                )
                continue

            free_tier_tokens = _safe_int(getattr(record, "free_tier_tokens", 0), default=0)
            if free_tier_tokens < 0:
                free_tier_tokens = 0

            if provider not in LLM_PRICING:
                LLM_PRICING[provider] = {}

            LLM_PRICING[provider][model] = ProviderCost(
                input=input_cost,
                output=output_cost,
                free_tier_tokens=free_tier_tokens
            )

            # Update default if explicitly provided or missing.
            if model == "default" or "default" not in LLM_PRICING[provider]:
                LLM_PRICING[provider]["default"] = LLM_PRICING[provider][model]

    except Exception as e:
        # Fail open but emit audit log for observability
        logger.error("llm_pricing_refresh_failed", error=str(e), error_type=type(e).__name__)
        return
