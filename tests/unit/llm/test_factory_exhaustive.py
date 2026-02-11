import pytest
from typing import Dict
from unittest.mock import MagicMock, patch
from app.shared.llm.factory import LLMFactory, AnalysisComplexity

class TestFactoryExhaustive:
    """Exhaustive tests for LLMFactory."""

    def test_select_provider_fallbacks(self):
        """Test waterfall fallbacks when preferred provider is missing (lines 83-118)."""
        with patch("app.shared.llm.factory.get_settings") as mock_settings:
            # 1. SIMPLE: Groq missing -> Google
            mock_settings.return_value.GROQ_API_KEY = None
            mock_settings.return_value.GOOGLE_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 10)
            assert prov == "google"
            
            # 2. SIMPLE: Groq and Google missing -> OpenAI
            mock_settings.return_value.GOOGLE_API_KEY = None
            mock_settings.return_value.OPENAI_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 10)
            assert prov == "openai"
            
            # 3. MEDIUM: Google missing -> Groq
            mock_settings.return_value.GOOGLE_API_KEY = None
            mock_settings.return_value.GROQ_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 5000) # ~1250 tokens (medium)
            assert prov == "groq"
            
            # 4. MEDIUM: Google and Groq missing -> OpenAI
            mock_settings.return_value.GROQ_API_KEY = None
            mock_settings.return_value.OPENAI_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 5000)
            assert prov == "openai"
            
            # 5. COMPLEX: OpenAI missing -> Google
            mock_settings.return_value.OPENAI_API_KEY = None
            mock_settings.return_value.GOOGLE_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 20000) # ~5000 tokens (complex)
            assert prov == "google"
            
            # 6. COMPLEX: OpenAI and Google missing -> Groq
            mock_settings.return_value.GOOGLE_API_KEY = None
            mock_settings.return_value.GROQ_API_KEY = "key"
            prov, _ = LLMFactory.select_provider("x" * 20000)
            assert prov == "groq"

    def test_estimate_cost(self):
        """Test cost estimation logic (lines 120-139)."""
        # Testing with a known provider pricing map
        # Assuming pricing_data.py has 'openai': {'default': {'input': 0.15, 'output': 0.60}} 
        # (Actually I should check pricing_data.py or just trust the logic)
        
        # Test with a provider that exists
        with patch("app.shared.llm.factory.LLM_PRICING", {
            "test_prov": {"default": MagicMock(input=0.15, output=0.60)}
        }):
            # 1M input, 1M output -> 0.15 + 0.60 = 0.75
            cost = LLMFactory.estimate_cost("test_prov", 1_000_000, 1_000_000)
            assert cost == 0.75
            
            # Test empty provider
            assert LLMFactory.estimate_cost("unknown", 100, 100) == 0.0

    def test_create_unsupported_provider(self):
        """Test create with unsupported provider (line 164)."""
        with patch("app.shared.llm.factory.get_settings"):
            with pytest.raises(ValueError, match="Unsupported provider"):
                LLMFactory.create(provider="unsupported")

    @pytest.mark.asyncio
    async def test_create_smart(self):
        """Test create_smart convenience method (lines 173-200)."""
        with patch.object(LLMFactory, "select_provider", return_value=("groq", AnalysisComplexity.SIMPLE)), \
             patch.object(LLMFactory, "create", return_value=MagicMock()) as mock_create:
            
            llm, prov, comp = LLMFactory.create_smart("input text")
            
            assert prov == "groq"
            assert comp == AnalysisComplexity.SIMPLE
            assert mock_create.called

    def test_estimate_tokens(self):
        """Test token estimation (lines 36-42)."""
        assert LLMFactory.estimate_tokens("1234") == 1
        assert LLMFactory.estimate_tokens("") == 0

    def test_validate_api_key(self):
        """Test API key validation logic."""
        # Valid key
        LLMFactory.validate_api_key("test", "sk-valid-key-length-check-passed-123")
        
        # Missing key
        with pytest.raises(ValueError, match="is not configured"):
            LLMFactory.validate_api_key("test", None)
            
        # Placeholder
        with pytest.raises(ValueError, match="contains a placeholder"):
            LLMFactory.validate_api_key("test", "sk-xxx-placeholder")
            
        # Too short
        with pytest.raises(ValueError, match="is too short"):
            LLMFactory.validate_api_key("test", "short")

    def test_create_valid_provider(self):
        """Test create with valid providers."""
        with patch("app.shared.llm.factory.get_settings") as mock_settings, \
             patch("app.shared.llm.providers.OpenAIProvider") as MockOpenAI, \
             patch("app.shared.llm.providers.AnthropicProvider") as MockAnthropic:
            
            # OpenAI
            mock_openai_instance = MockOpenAI.return_value
            LLMFactory.create(provider="openai", api_key="sk-test", model="gpt-4")
            mock_openai_instance.create_model.assert_called_with(model="gpt-4", api_key="sk-test")
            
            # Anthropic
            mock_anthropic_instance = MockAnthropic.return_value
            LLMFactory.create(provider="anthropic", api_key="sk-test")
            mock_anthropic_instance.create_model.assert_called()
