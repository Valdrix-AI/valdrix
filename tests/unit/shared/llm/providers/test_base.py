import pytest
from unittest.mock import MagicMock
from app.shared.llm.providers.base import BaseProvider

# Mock Langchain if not available or causes issues (though it should be fine)
# For BaseProvider testing we don't strictly need real Langchain classes if we just return Mock
from langchain_core.language_models.chat_models import BaseChatModel


class ConcreteProvider(BaseProvider):
    """Concrete implementation for testing BaseProvider."""

    def create_model(self, model=None, api_key=None):
        return MagicMock(spec=BaseChatModel)


class TestBaseProvider:
    def test_validate_api_key_valid(self):
        """Test validation with a valid API key."""
        provider = ConcreteProvider()
        # Valid key: no placeholders, length >= 20
        valid_key = "sk-valid-api-key-that-is-long-enough-12345"
        # Should not raise
        provider.validate_api_key(valid_key, "test_provider")

    def test_validate_api_key_missing(self):
        """Test validation raises ValueError when key is missing."""
        provider = ConcreteProvider()
        with pytest.raises(ValueError, match="TEST_PROVIDER_API_KEY not configured"):
            provider.validate_api_key(None, "test_provider")

        with pytest.raises(ValueError, match="TEST_PROVIDER_API_KEY not configured"):
            provider.validate_api_key("", "test_provider")

    def test_validate_api_key_placeholder(self):
        """Test validation raises ValueError for placeholder keys."""
        provider = ConcreteProvider()
        placeholders = ["sk-xxx", "change-me", "your-key-here", "default_key"]

        for ph in placeholders:
            with pytest.raises(ValueError, match="Key contains a placeholder value"):
                provider.validate_api_key(
                    f"some-prefix-{ph}-some-suffix", "test_provider"
                )

    def test_validate_api_key_too_short(self):
        """Test validation raises ValueError for short keys."""
        provider = ConcreteProvider()
        short_key = "short-key-123"  # length 13
        with pytest.raises(ValueError, match="Key is too short"):
            provider.validate_api_key(short_key, "test_provider")

    def test_create_model_abstract(self):
        """Test that BaseProvider cannot be instantiated directly."""
        # This checks standard ABC behavior
        with pytest.raises(TypeError):
            BaseProvider()
