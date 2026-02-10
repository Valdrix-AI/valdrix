import pytest
"""
Tests for LLM Logic - Provider Selection and Smart Factory
"""
from typing import Dict
from unittest.mock import MagicMock, patch
from app.shared.llm.factory import LLMFactory, LLMProviderSelector, AnalysisComplexity


def test_estimate_tokens():
    """Test token estimation logic (4 chars per token)."""
    assert LLMProviderSelector.estimate_tokens("1234") == 1
    assert LLMProviderSelector.estimate_tokens("12345678") == 2
    assert LLMProviderSelector.estimate_tokens("") == 0


def test_classify_complexity():
    """Test complexity classification based on token counts."""
    assert LLMProviderSelector.classify_complexity(500) == AnalysisComplexity.SIMPLE
    assert LLMProviderSelector.classify_complexity(1500) == AnalysisComplexity.MEDIUM
    assert LLMProviderSelector.classify_complexity(5000) == AnalysisComplexity.COMPLEX


def test_select_provider_byok_priority():
    """Test that BYOK provider always takes priority."""
    with patch("app.shared.llm.factory.get_settings") as _:
        provider, complexity = LLMProviderSelector.select_provider(
            "short text", tenant_byok_provider="openai"
        )
        assert provider == "openai"
        # BYOK forced to MEDIUM by default in implementation
        assert complexity == AnalysisComplexity.MEDIUM


def test_select_provider_waterfall_simple():
    """Test waterfall selection for SIMPLE complexity (Groq preferred)."""
    with patch("app.shared.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value.GROQ_API_KEY = "sk-groq-valid-key-long-enough"
        
        provider, complexity = LLMProviderSelector.select_provider("A" * 100) # ~25 tokens
        assert complexity == AnalysisComplexity.SIMPLE
        assert provider == "groq"


def test_select_provider_waterfall_medium():
    """Test waterfall selection for MEDIUM complexity (Google preferred)."""
    with patch("app.shared.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value.GROQ_API_KEY = "sk-groq-valid-key-long-enough"
        mock_settings.return_value.GOOGLE_API_KEY = "google-valid-key-long-enough"
        
        provider, complexity = LLMProviderSelector.select_provider("A" * 6000) # ~1500 tokens
        assert complexity == AnalysisComplexity.MEDIUM
        assert provider == "google"


def test_select_provider_waterfall_complex():
    """Test waterfall selection for COMPLEX complexity (OpenAI preferred)."""
    with patch("app.shared.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = "sk-openai-valid-key-long-enough"
        
        provider, complexity = LLMProviderSelector.select_provider("A" * 20000) # ~5000 tokens
        assert complexity == AnalysisComplexity.COMPLEX
        assert provider == "openai"


def test_estimate_cost_groq():
    """Test cost estimation for Groq."""
    cost = LLMProviderSelector.estimate_cost("groq", 1000, 500)
    # Expected: (1000*0.59 + 500*0.79) / 1,000,000 = 0.000985
    assert abs(cost - 0.000985) < 1e-6



def test_estimate_cost_paid_provider():
    """Test cost estimation for paid providers."""
    # OpenAI costs from PROVIDER_COSTS: 0.00015 input, 0.0006 output per 1K
    cost = LLMProviderSelector.estimate_cost("openai", 1000, 1000)
    expected = 0.00015 + 0.0006
    assert abs(cost - expected) < 1e-6



@pytest.mark.asyncio
async def test_llm_factory_create_smart():
    """Test smart creation combining selection and instantiation."""
    with patch("app.shared.llm.factory.LLMProviderSelector.select_provider") as mock_select:
        mock_select.return_value = ("groq", AnalysisComplexity.SIMPLE)
        
        with patch("app.shared.llm.factory.LLMFactory.create") as mock_create:
            mock_create.return_value = MagicMock()
            
            llm, provider, complexity = LLMFactory.create_smart("input text")
            
            assert provider == "groq"
            assert complexity == AnalysisComplexity.SIMPLE
            mock_create.assert_called_with(provider="groq", api_key=None)

@pytest.mark.asyncio
async def test_llm_factory_create_google():
    """Test creating Google Gemini client."""
    with patch("app.shared.llm.providers.GoogleProvider") as MockProvider:
        mock_instance = MockProvider.return_value
        
        with patch("app.shared.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.GOOGLE_API_KEY = "google-valid-key-long-enough"
            mock_settings.return_value.GOOGLE_MODEL = "gemini-flash"
            
            LLMFactory.create(provider="google")
            
            mock_instance.create_model.assert_called_with(model=None, api_key=None)

@pytest.mark.asyncio
async def test_llm_factory_create_groq():
    """Test creating Groq client."""
    with patch("app.shared.llm.providers.GroqProvider") as MockProvider:
        mock_instance = MockProvider.return_value
        
        with patch("app.shared.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "groq-valid-key-long-enough"
            mock_settings.return_value.GROQ_MODEL = "llama-3"
            
            LLMFactory.create(provider="groq")
            
            mock_instance.create_model.assert_called_with(model=None, api_key=None)

def test_llm_factory_create_unsupported():
    """Test error when creating unsupported provider."""
    with pytest.raises(ValueError, match="Unsupported provider"):
        LLMFactory.create(provider="unknown-ai")
