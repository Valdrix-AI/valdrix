from typing import Optional, Tuple
from enum import Enum
from langchain_core.language_models.chat_models import BaseChatModel
import structlog
from app.shared.core.config import get_settings
from .pricing_data import LLM_PRICING

logger = structlog.get_logger()

class AnalysisComplexity(str, Enum):
    """Analysis complexity levels for provider selection."""
    SIMPLE = "simple"    # < 1000 tokens, use Groq (free)
    MEDIUM = "medium"    # 1000-4000 tokens, use Gemini (cheap)
    COMPLEX = "complex"  # > 4000 tokens, use GPT-4o-mini (best)

class LLMFactory:
    @staticmethod
    def validate_api_key(provider: str, api_key: Optional[str]) -> None:
        """
        Validates the format and presence of an LLM API key.
        Prevents usage of placeholders and provides early feedback.
        """
        if not api_key:
            raise ValueError(f"LLM API key for provider '{provider}' is not configured.")
        
        # Check for placeholders
        if "xxx" in api_key.lower() or "change-me" in api_key.lower():
            # Test expects "contains a placeholder"
            raise ValueError(f"LLM API key for '{provider}' contains a placeholder. Use a real key.")
            
        # Basic length validation
        if len(api_key) < 20: 
            # Test expects "too short"
            raise ValueError(f"LLM API key for '{provider}' is too short.")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough token estimation (4 chars per token).
        Good enough for provider selection.
        """
        return len(text) // 4
    
    @staticmethod
    def classify_complexity(token_count: int) -> AnalysisComplexity:
        """Classify analysis complexity based on token count."""
        if token_count < 1000:
            return AnalysisComplexity.SIMPLE
        elif token_count < 4000:
            return AnalysisComplexity.MEDIUM
        else:
            return AnalysisComplexity.COMPLEX
    
    @staticmethod
    def select_provider(
        input_text: str,
        tenant_byok_provider: Optional[str] = None
    ) -> Tuple[str, AnalysisComplexity]:
        """
        Select optimal provider based on input size and tenant config.
        
        Args:
            input_text: The text to analyze (for token estimation)
            tenant_byok_provider: Tenant's BYOK provider if configured
        
        Returns:
            Tuple of (provider_name, complexity)
        """
        settings = get_settings()
        
        # If tenant has BYOK, always use their configured provider
        if tenant_byok_provider:
            logger.info(
                "llm_provider_byok",
                provider=tenant_byok_provider
            )
            return tenant_byok_provider, AnalysisComplexity.MEDIUM
        
        # Estimate tokens
        token_estimate = LLMFactory.estimate_tokens(input_text)
        complexity = LLMFactory.classify_complexity(token_estimate)
        
        # Waterfall selection
        if complexity == AnalysisComplexity.SIMPLE:
            # Use Groq free tier for small analyses
            if settings.GROQ_API_KEY:
                provider = "groq"
            elif settings.GOOGLE_API_KEY:
                provider = "google"
            else:
                provider = "openai"
        
        elif complexity == AnalysisComplexity.MEDIUM:
            # Use Gemini for medium (cheapest paid option)
            if settings.GOOGLE_API_KEY:
                provider = "google"
            elif settings.GROQ_API_KEY:
                provider = "groq"
            else:
                provider = "openai"
        
        else:  # COMPLEX
            # Use GPT-4o-mini for complex (best quality)
            if settings.OPENAI_API_KEY:
                provider = "openai"
            elif settings.GOOGLE_API_KEY:
                provider = "google"
            else:
                provider = "groq"
        
        logger.info(
            "llm_provider_selected",
            provider=provider,
            complexity=complexity.value,
            estimated_tokens=token_estimate
        )
        
        return provider, complexity
    
    @staticmethod
    def estimate_cost(
        provider: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Estimate cost for a provider call in USD."""
        # Use 'default' model pricing for the provider
        provider_data = LLM_PRICING.get(provider, {})
        costs = provider_data.get("default")
        
        if not costs:
            return 0.0
        
        # ProviderCost supports both .input and ['input']
        # Pricing is Per Million Tokens
        input_cost = (input_tokens / 1_000_000) * costs.input
        output_cost = (output_tokens / 1_000_000) * costs.output
        
        return input_cost + output_cost


    @staticmethod
    def create(provider: str = None, model: str = None, api_key: str = None) -> BaseChatModel:
        """
        Create an LLM client for the specified provider and model.
        DELEGATION: Now uses modular provider classes for model creation.
        """
        from app.shared.llm.providers import (
            OpenAIProvider,
            AnthropicProvider,
            GoogleProvider,
            GroqProvider
        )
        
        settings = get_settings()
        # Use configured provider if none specified
        effective_provider = (provider or settings.LLM_PROVIDER or "groq").lower()
        
        providers = {
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "claude": AnthropicProvider(),
            "google": GoogleProvider(),
            "groq": GroqProvider()
        }
        
        if effective_provider not in providers:
            raise ValueError(f"Unsupported provider: {effective_provider}")
            
        logger.info("Initializing LLM (Modular)", provider=effective_provider, model=model, byok=api_key is not None)
        return providers[effective_provider].create_model(model=model, api_key=api_key)
    
    @staticmethod
    def create_smart(
        input_text: str,
        tenant_byok_provider: Optional[str] = None,
        tenant_byok_key: Optional[str] = None
    ) -> Tuple[BaseChatModel, str, AnalysisComplexity]:
        """
        Create an LLM client with smart provider selection.
        
        Uses waterfall strategy to minimize costs:
        1. Groq (free) for small analyses
        2. Gemini (cheap) for medium
        3. GPT-4o-mini (quality) for complex
        
        Returns:
            Tuple of (llm_client, provider_name, complexity)
        """
        provider, complexity = LLMFactory.select_provider(
            input_text=input_text,
            tenant_byok_provider=tenant_byok_provider
        )
        
        llm = LLMFactory.create(
            provider=provider,
            api_key=tenant_byok_key if tenant_byok_provider else None
        )
        
        return llm, provider, complexity


LLMProviderSelector = LLMFactory
