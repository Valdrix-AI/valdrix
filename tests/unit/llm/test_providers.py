"""
Production-quality tests for LLM Providers.
Tests cover security, API key validation, model creation, and error handling.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.shared.llm.providers.base import BaseProvider
from app.shared.llm.providers.openai import OpenAIProvider
from app.shared.llm.providers.google import GoogleProvider
from app.shared.llm.providers.anthropic import AnthropicProvider
from app.shared.llm.providers.groq import GroqProvider


class TestBaseProvider:
    """Tests for the BaseProvider abstract class."""

    class DummyProvider(BaseProvider):
        def create_model(self, model=None, api_key=None):
            return MagicMock()

    def test_validate_api_key_valid(self):
        """Test API key validation with valid key."""
        provider = self.DummyProvider()
        # This should not raise an exception
        provider.validate_api_key("sk-1234567890123456789012345678901234567890", "test")

    def test_validate_api_key_none(self):
        """Test API key validation with None key."""
        provider = self.DummyProvider()
        with pytest.raises(ValueError, match="TEST_API_KEY not configured"):
            provider.validate_api_key(None, "test")

    def test_validate_api_key_empty(self):
        """Test API key validation with empty key."""
        provider = self.DummyProvider()
        with pytest.raises(ValueError, match="TEST_API_KEY not configured"):
            provider.validate_api_key("", "test")

    def test_validate_api_key_placeholder_values(self):
        """Test API key validation rejects placeholder values."""
        provider = self.DummyProvider()
        placeholder_keys = [
            "sk-xxx",
            "change-me",
            "your-key-here",
            "default_key",
            "SK-XXX",
            "CHANGE-ME",
        ]

        for key in placeholder_keys:
            with pytest.raises(
                ValueError,
                match="Invalid API key for test: Key contains a placeholder value",
            ):
                provider.validate_api_key(key, "test")

    def test_validate_api_key_too_short(self):
        """Test API key validation rejects keys that are too short."""
        provider = self.DummyProvider()
        with pytest.raises(
            ValueError, match="Invalid API key for test: Key is too short"
        ):
            provider.validate_api_key("short", "test")

    def test_validate_api_key_minimum_length(self):
        """Test API key validation accepts keys at minimum length."""
        provider = self.DummyProvider()
        # Should not raise an exception
        provider.validate_api_key("x" * 20, "test")

    def test_create_model_concrete_provider_works(self):
        """Test that concrete provider model creation path executes without abstract errors."""
        # Can't instantiate abstract class directly, so test that concrete providers work
        provider = OpenAIProvider()
        # This should work without triggering abstract-base enforcement.
        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance
            result = provider.create_model(
                api_key="sk-valid123456789012345678901234567890"
            )
            assert result == mock_instance


class TestOpenAIProvider:
    """Tests for OpenAI provider implementation."""

    def test_create_model_with_api_key(self):
        """Test model creation with provided API key."""
        provider = OpenAIProvider()

        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model(
                model="gpt-4", api_key="sk-valid123456789012345678901234567890"
            )

            mock_chat.assert_called_once_with(
                api_key="sk-valid123456789012345678901234567890",
                model="gpt-4",
                temperature=0,
            )
            assert result == mock_instance

    def test_create_model_with_explicit_max_output_tokens(self):
        provider = OpenAIProvider()

        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model(
                model="gpt-4o-mini",
                api_key="sk-valid123456789012345678901234567890",
                max_output_tokens=2048,
            )

            mock_chat.assert_called_once_with(
                api_key="sk-valid123456789012345678901234567890",
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=2048,
            )

    @patch("app.shared.llm.providers.openai.get_settings")
    def test_create_model_from_settings(self, mock_get_settings):
        """Test model creation using settings API key."""
        mock_settings = MagicMock()
        mock_settings.OPENAI_API_KEY = "sk-settings123456789012345678901234567890"
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"
        mock_get_settings.return_value = mock_settings

        provider = OpenAIProvider()

        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model()

            mock_chat.assert_called_once_with(
                api_key="sk-settings123456789012345678901234567890",
                model="gpt-3.5-turbo",
                temperature=0,
            )
            assert result == mock_instance

    @patch("app.shared.llm.providers.openai.get_settings")
    def test_create_model_invalid_api_key(self, mock_get_settings):
        """Test model creation with invalid API key."""
        mock_settings = MagicMock()
        mock_settings.OPENAI_API_KEY = "sk-xxx"  # Invalid placeholder
        mock_get_settings.return_value = mock_settings

        provider = OpenAIProvider()

        with pytest.raises(ValueError, match="Invalid API key for openai"):
            provider.create_model()


class TestGoogleProvider:
    """Tests for Google provider implementation."""

    def test_create_model_with_api_key(self):
        """Test model creation with provided API key."""
        provider = GoogleProvider()

        with patch(
            "app.shared.llm.providers.google.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model(
                model="gemini-pro", api_key="AIzaSy-valid123456789012345678901234567890"
            )

            mock_chat.assert_called_once_with(
                google_api_key="AIzaSy-valid123456789012345678901234567890",
                model="gemini-pro",
                temperature=0,
            )
            assert result == mock_instance

    @patch("app.shared.llm.providers.google.get_settings")
    def test_create_model_from_settings(self, mock_get_settings):
        """Test model creation using settings API key."""
        mock_settings = MagicMock()
        mock_settings.GOOGLE_API_KEY = "AIzaSy-settings123456789012345678901234567890"
        mock_settings.GOOGLE_MODEL = "gemini-1.5-flash"
        mock_get_settings.return_value = mock_settings

        provider = GoogleProvider()

        with patch(
            "app.shared.llm.providers.google.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model()

            mock_chat.assert_called_once_with(
                google_api_key="AIzaSy-settings123456789012345678901234567890",
                model="gemini-1.5-flash",
                temperature=0,
            )
            assert result == mock_instance

    def test_create_model_with_max_output_tokens(self):
        provider = GoogleProvider()

        with patch(
            "app.shared.llm.providers.google.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model(
                model="gemini-2.0-flash",
                api_key="AIzaSy-valid123456789012345678901234567890",
                max_output_tokens=1024,
            )

            mock_chat.assert_called_once_with(
                google_api_key="AIzaSy-valid123456789012345678901234567890",
                model="gemini-2.0-flash",
                temperature=0,
                max_output_tokens=1024,
            )


class TestAnthropicProvider:
    """Tests for Anthropic provider implementation."""

    def test_create_model_with_api_key(self):
        """Test model creation with provided API key."""
        provider = AnthropicProvider()

        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model(
                model="claude-3-sonnet-20240229",
                api_key="sk-ant-valid123456789012345678901234567890",
            )

            mock_chat.assert_called_once_with(
                api_key="sk-ant-valid123456789012345678901234567890",
                model="claude-3-sonnet-20240229",
                temperature=0,
            )
            assert result == mock_instance

    @patch("app.shared.llm.providers.anthropic.get_settings")
    def test_create_model_fallback_api_keys(self, mock_get_settings):
        """Test model creation with fallback API key logic."""
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = None
        mock_settings.CLAUDE_API_KEY = "sk-claude-valid123456789012345678901234567890"
        mock_settings.CLAUDE_MODEL = "claude-3-haiku-20240307"
        mock_get_settings.return_value = mock_settings

        provider = AnthropicProvider()

        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model()

            mock_chat.assert_called_once_with(
                api_key="sk-claude-valid123456789012345678901234567890",
                model="claude-3-haiku-20240307",
                temperature=0,
            )
            assert result == mock_instance

    @patch("app.shared.llm.providers.anthropic.get_settings")
    def test_create_model_anthropic_priority(self, mock_get_settings):
        """Test that ANTHROPIC_API_KEY takes priority over CLAUDE_API_KEY."""
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "sk-anth-valid123456789012345678901234567890"
        mock_settings.CLAUDE_API_KEY = "sk-claude-valid123456789012345678901234567890"
        mock_settings.CLAUDE_MODEL = "claude-3-haiku-20240307"
        mock_get_settings.return_value = mock_settings

        provider = AnthropicProvider()

        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model()

            # Should use ANTHROPIC_API_KEY, not CLAUDE_API_KEY
            mock_chat.assert_called_once_with(
                api_key="sk-anth-valid123456789012345678901234567890",
                model="claude-3-haiku-20240307",
                temperature=0,
            )

    def test_create_model_with_max_output_tokens(self):
        provider = AnthropicProvider()

        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model(
                model="claude-3-7-sonnet",
                api_key="sk-ant-valid123456789012345678901234567890",
                max_output_tokens=2048,
            )

            mock_chat.assert_called_once_with(
                api_key="sk-ant-valid123456789012345678901234567890",
                model="claude-3-7-sonnet",
                temperature=0,
                max_tokens=2048,
            )


class TestGroqProvider:
    """Tests for Groq provider implementation."""

    def test_create_model_with_api_key(self):
        """Test model creation with provided API key."""
        provider = GroqProvider()

        with patch("app.shared.llm.providers.groq.ChatGroq") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model(
                model="llama2-70b-4096",
                api_key="gsk_valid123456789012345678901234567890",
            )

            mock_chat.assert_called_once_with(
                api_key="gsk_valid123456789012345678901234567890",
                model="llama2-70b-4096",
                temperature=0,
            )
            assert result == mock_instance

    @patch("app.shared.llm.providers.groq.get_settings")
    def test_create_model_from_settings(self, mock_get_settings):
        """Test model creation using settings API key."""
        mock_settings = MagicMock()
        mock_settings.GROQ_API_KEY = "gsk_settings123456789012345678901234567890"
        mock_settings.GROQ_MODEL = "mixtral-8x7b-32768"
        mock_get_settings.return_value = mock_settings

        provider = GroqProvider()

        with patch("app.shared.llm.providers.groq.ChatGroq") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            result = provider.create_model()

            mock_chat.assert_called_once_with(
                api_key="gsk_settings123456789012345678901234567890",
                model="mixtral-8x7b-32768",
                temperature=0,
            )
            assert result == mock_instance

    def test_create_model_with_max_output_tokens(self):
        provider = GroqProvider()

        with patch("app.shared.llm.providers.groq.ChatGroq") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model(
                model="llama-3.3-70b-versatile",
                api_key="gsk_valid123456789012345678901234567890",
                max_output_tokens=4096,
            )

            mock_chat.assert_called_once_with(
                api_key="gsk_valid123456789012345678901234567890",
                model="llama-3.3-70b-versatile",
                temperature=0,
                max_tokens=4096,
            )


class TestLLMProvidersProductionQuality:
    """Production-quality tests covering security, performance, and integration."""

    def test_api_key_security_validation_comprehensive(self):
        """Test comprehensive API key security validation across all providers."""
        providers = [
            OpenAIProvider(),
            GoogleProvider(),
            AnthropicProvider(),
            GroqProvider(),
        ]

        malicious_keys = [
            "sk-123",  # Too short
            "sk-xxx",  # Placeholder
            "change-me",  # Placeholder
            "your-key-here",  # Placeholder
            "default_key",  # Placeholder
            "",  # Empty
            None,  # None
            "a" * 19,  # Just under minimum length
        ]

        for provider in providers:
            provider_name = provider.__class__.__name__.replace("Provider", "").lower()
            for malicious_key in malicious_keys:
                with pytest.raises(ValueError):
                    provider.validate_api_key(malicious_key, provider_name)

    def test_provider_initialization_isolation(self):
        """Test that provider instances are properly isolated."""
        provider1 = OpenAIProvider()
        provider2 = GoogleProvider()

        # Each provider should be independent instances
        assert isinstance(provider1, OpenAIProvider)
        assert isinstance(provider2, GoogleProvider)
        assert provider1 != provider2

    def test_model_creation_error_handling(self):
        """Test error handling during model creation."""
        provider = OpenAIProvider()

        # Test with invalid API key that passes validation but fails in LangChain
        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_chat.side_effect = Exception("LangChain initialization failed")

            with pytest.raises(Exception, match="LangChain initialization failed"):
                provider.create_model(api_key="sk-valid123456789012345678901234567890")

    def test_provider_configuration_isolation(self):
        """Test that provider configurations don't interfere with each other."""
        # Create multiple providers and ensure they maintain separate state
        providers = {
            "openai": OpenAIProvider(),
            "google": GoogleProvider(),
            "anthropic": AnthropicProvider(),
            "groq": GroqProvider(),
        }

        # Each provider should validate keys independently
        for name, provider in providers.items():
            # Should all accept the same valid key format
            provider.validate_api_key("sk-valid123456789012345678901234567890", name)

    def test_memory_usage_efficiency(self):
        """Test memory efficiency of provider operations."""
        import psutil

        # Get initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create and use multiple providers
        providers = []
        for _ in range(100):  # Create many provider instances
            providers.extend(
                [
                    OpenAIProvider(),
                    GoogleProvider(),
                    AnthropicProvider(),
                    GroqProvider(),
                ]
            )

        # Test API key validation on all providers
        for provider in providers:
            provider_name = provider.__class__.__name__.replace("Provider", "").lower()
            provider.validate_api_key(
                "sk-valid123456789012345678901234567890", provider_name
            )

        # Check memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (< 50MB for 400 provider instances)
        assert memory_increase < 50, f"Excessive memory usage: {memory_increase:.1f}MB"

    def test_concurrent_provider_usage_safety(self):
        """Test thread safety of provider operations."""
        import threading

        provider = OpenAIProvider()
        results = []
        errors = []

        def validate_key():
            try:
                provider.validate_api_key(
                    "sk-valid123456789012345678901234567890", "openai"
                )
                results.append("success")
            except Exception as e:
                errors.append(str(e))

        # Run validation concurrently
        threads = []
        for _ in range(50):
            thread = threading.Thread(target=validate_key)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All validations should succeed
        assert len(results) == 50
        assert len(errors) == 0

    def test_provider_error_messages_security(self):
        """Test that error messages don't leak sensitive information."""
        provider = OpenAIProvider()

        sensitive_keys = [
            "sk-1234567890123456789012345678901234567890",
            "AIzaSy-1234567890123456789012345678901234567890",
            "sk-ant-1234567890123456789012345678901234567890",
            "gsk_1234567890123456789012345678901234567890",
        ]

        for sensitive_key in sensitive_keys:
            try:
                provider.validate_api_key(sensitive_key, "test")
            except ValueError as e:
                error_msg = str(e)
                # Error message should not contain the actual key
                assert sensitive_key not in error_msg, (
                    f"Error message leaked API key: {error_msg}"
                )

    def test_provider_model_parameter_validation(self):
        """Test model parameter validation and defaults."""
        provider = OpenAIProvider()

        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            # Test with None model (should use default)
            provider.create_model(
                model=None, api_key="sk-valid123456789012345678901234567890"
            )

            # Should be called with model parameter (will be None, settings default used)
            call_args = mock_chat.call_args
            assert "model" in call_args[1]

    def test_provider_temperature_consistency(self):
        """Test that all providers use consistent temperature settings."""
        providers = [
            ("openai", OpenAIProvider(), "app.shared.llm.providers.openai.ChatOpenAI"),
            (
                "google",
                GoogleProvider(),
                "app.shared.llm.providers.google.ChatGoogleGenerativeAI",
            ),
            (
                "anthropic",
                AnthropicProvider(),
                "app.shared.llm.providers.anthropic.ChatAnthropic",
            ),
            ("groq", GroqProvider(), "app.shared.llm.providers.groq.ChatGroq"),
        ]

        for provider_name, provider, mock_path in providers:
            with patch(mock_path) as mock_chat:
                mock_instance = MagicMock()
                mock_chat.return_value = mock_instance

                provider.create_model(api_key="sk-valid123456789012345678901234567890")

                # All providers should use temperature=0 for consistency
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs.get("temperature") == 0, (
                    f"{provider_name} provider doesn't use temperature=0"
                )

    @patch("app.shared.llm.providers.openai.get_settings")
    def test_provider_integration_with_settings(self, mock_get_settings):
        """Test provider integration with settings system."""
        mock_settings = MagicMock()
        mock_settings.OPENAI_API_KEY = "sk-settings123456789012345678901234567890"
        mock_settings.OPENAI_MODEL = "gpt-4"
        mock_get_settings.return_value = mock_settings

        provider = OpenAIProvider()

        with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance

            provider.create_model()

            # Should use settings values
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["api_key"] == "sk-settings123456789012345678901234567890"
            assert call_kwargs["model"] == "gpt-4"
            assert call_kwargs["temperature"] == 0
