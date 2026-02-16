from typing import Dict
import pytest
from unittest.mock import patch
from app.shared.llm.factory import LLMFactory, AnalysisComplexity


def test_validate_api_key():
    """Test API key validation logic."""
    LLMFactory.validate_api_key("openai", "sk-valid-key-that-is-long-enough-12345")

    # Missing
    with pytest.raises(ValueError, match="not configured"):
        LLMFactory.validate_api_key("openai", None)

    # Placeholder
    with pytest.raises(ValueError, match="placeholder"):
        LLMFactory.validate_api_key("openai", "sk-xxx-placeholder")

    # Too short
    with pytest.raises(ValueError, match="too short"):
        LLMFactory.validate_api_key("openai", "short")


def test_classify_complexity():
    """Test token-based complexity classification."""
    assert LLMFactory.classify_complexity(500) == AnalysisComplexity.SIMPLE
    assert LLMFactory.classify_complexity(2000) == AnalysisComplexity.MEDIUM
    assert LLMFactory.classify_complexity(5000) == AnalysisComplexity.COMPLEX


def test_select_provider_waterfall():
    """Test provider selection logic."""
    # Mock settings
    with patch("app.shared.llm.factory.get_settings") as mock_settings:
        # Default scenario: All keys present
        mock_settings.return_value.GROQ_API_KEY = "key"
        mock_settings.return_value.GOOGLE_API_KEY = "key"
        mock_settings.return_value.OPENAI_API_KEY = "key"

        # 1. Simple text -> Groq (Free)
        prov, comp = LLMFactory.select_provider(
            "short text " * 10
        )  # ~100 chars, ~25 tokens
        assert prov == "groq"
        assert comp == AnalysisComplexity.SIMPLE

        # 2. Medium text -> Google (Cheap)
        prov, comp = LLMFactory.select_provider(
            "medium " * 1000
        )  # ~7000 chars, ~1750 tokens
        assert prov == "google"  # Medium prefers Google if available
        assert comp == AnalysisComplexity.MEDIUM

        # 3. Complex text -> OpenAI (Best)
        prov, comp = LLMFactory.select_provider(
            "long " * 4000
        )  # ~20000 chars, ~5000 tokens
        assert prov == "openai"  # Complex prefers OpenAI
        assert comp == AnalysisComplexity.COMPLEX


def test_select_provider_byok():
    """Test BYOK override."""
    with patch("app.shared.llm.factory.get_settings"):
        prov, comp = LLMFactory.select_provider("text", tenant_byok_provider="azure")
        assert prov == "azure"
