import pytest
from unittest.mock import MagicMock, patch
from app.services.llm.factory import LLMFactory
from app.services.llm.providers.openai import OpenAIProvider
from app.services.llm.providers.anthropic import AnthropicProvider

@pytest.mark.parametrize("provider,expected_class", [
    ("openai", "ChatOpenAI"),
    ("anthropic", "ChatAnthropic"),
    ("claude", "ChatAnthropic"),
    # Add others as needed
])
def test_factory_creates_correct_provider(provider, expected_class):
    """Verifies that LLMFactory delegates to the correct provider class."""
    with patch(f"app.services.llm.providers.{'Anthropic' if 'anthropic' in provider or 'claude' in provider else 'OpenAI'}Provider.create_model") as mock_create:
        mock_model = MagicMock()
        mock_create.return_value = mock_model
        
        result = LLMFactory.create(provider=provider, api_key="sk-test-key-long-enough-for-validation")
        
        assert result == mock_model
        mock_create.assert_called_once()

def test_factory_invalid_provider():
    """Verifies that an unsupported provider raises a ValueError."""
    with pytest.raises(ValueError, match="Unsupported provider"):
        LLMFactory.create(provider="unknown-provider")

def test_api_key_validation_failure():
    """Verifies that invalid API keys (placeholders or too short) are rejected."""
    from app.services.llm.providers.openai import OpenAIProvider
    provider = OpenAIProvider()
    
    with pytest.raises(ValueError, match="not configured"):
        provider.create_model(api_key=None)
        
    with pytest.raises(ValueError, match="contains a placeholder"):
        provider.create_model(api_key="sk-xxx-placeholder")
        
    with pytest.raises(ValueError, match="too short"):
        provider.create_model(api_key="short-key")
