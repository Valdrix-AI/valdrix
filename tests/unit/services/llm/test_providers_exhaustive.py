"""
Exhaustive tests for LLM Providers to achieve 100% coverage.
Covers: Groq, Google, OpenAI, Anthropic
"""
import pytest
from unittest.mock import patch
from app.shared.llm.providers.groq import GroqProvider 
from app.shared.llm.providers.google import GoogleProvider
from app.shared.llm.providers.openai import OpenAIProvider
from app.shared.llm.providers.anthropic import AnthropicProvider

# Helper for valid length keys (>20 chars)
VALID_KEY_GROQ = "gsk_valid_key_long_enough_for_validation_123"
VALID_KEY_GOOGLE = "google_valid_key_long_enough_for_validation_123"
VALID_KEY_OPENAI = "sk-openai_valid_key_long_enough_for_validation"
VALID_KEY_ANTHROPIC = "sk-ant_valid_key_long_enough_for_validation_12"

# --- Groq Provider Tests ---

def test_groq_provider_defaults():
    """Test GroqProvider with default settings."""
    with patch("app.shared.llm.providers.groq.get_settings") as mock_settings:
        mock_settings.return_value.GROQ_API_KEY = VALID_KEY_GROQ
        mock_settings.return_value.GROQ_MODEL = "llama-3-8b"
        
        with patch("app.shared.llm.providers.groq.ChatGroq") as MockChat:
            provider = GroqProvider()
            model = provider.create_model()
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_GROQ,
                model="llama-3-8b",
                temperature=0
            )
            assert model == MockChat.return_value

def test_groq_provider_explicit():
    """Test GroqProvider with explicit arguments."""
    with patch("app.shared.llm.providers.groq.get_settings"):
        with patch("app.shared.llm.providers.groq.ChatGroq") as MockChat:
            provider = GroqProvider()
            provider.create_model(model="mixtral-8x7b", api_key=VALID_KEY_GROQ)
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_GROQ,
                model="mixtral-8x7b",
                temperature=0
            )

def test_groq_provider_missing_key():
    """Test GroqProvider raises error when API key is missing."""
    with patch("app.shared.llm.providers.groq.get_settings") as mock_settings:
        mock_settings.return_value.GROQ_API_KEY = None
        
        provider = GroqProvider()
        # Expect the message from validate_api_key for None
        with pytest.raises(ValueError, match="GROQ_API_KEY not configured"):
            provider.create_model()

# --- Google Provider Tests ---

def test_google_provider_defaults():
    """Test GoogleProvider with default settings."""
    with patch("app.shared.llm.providers.google.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_API_KEY = VALID_KEY_GOOGLE
        mock_settings.return_value.GOOGLE_MODEL = "gemini-pro"
        
        with patch("app.shared.llm.providers.google.ChatGoogleGenerativeAI") as MockChat:
            provider = GoogleProvider()
            provider.create_model()
            
            MockChat.assert_called_once_with(
                google_api_key=VALID_KEY_GOOGLE,
                model="gemini-pro",
                temperature=0
            )

def test_google_provider_explicit():
    """Test GoogleProvider with explicit arguments."""
    with patch("app.shared.llm.providers.google.get_settings"):
        with patch("app.shared.llm.providers.google.ChatGoogleGenerativeAI") as MockChat:
            provider = GoogleProvider()
            provider.create_model(model="gemini-ultra", api_key=VALID_KEY_GOOGLE)
            
            MockChat.assert_called_once_with(
                google_api_key=VALID_KEY_GOOGLE,
                model="gemini-ultra",
                temperature=0
            )

def test_google_provider_missing_key():
    """Test GoogleProvider raises error when API key is missing."""
    with patch("app.shared.llm.providers.google.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_API_KEY = None
        
        provider = GoogleProvider()
        with pytest.raises(ValueError, match="GOOGLE_API_KEY not configured"):
            provider.create_model()

# --- OpenAI Provider Tests ---

def test_openai_provider_defaults():
    """Test OpenAIProvider with default settings."""
    with patch("app.shared.llm.providers.openai.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = VALID_KEY_OPENAI
        mock_settings.return_value.OPENAI_MODEL = "gpt-4"
        
        with patch("app.shared.llm.providers.openai.ChatOpenAI") as MockChat:
            provider = OpenAIProvider()
            provider.create_model()
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_OPENAI,
                model="gpt-4",
                temperature=0
            )

def test_openai_provider_explicit():
    """Test OpenAIProvider with explicit arguments."""
    with patch("app.shared.llm.providers.openai.get_settings"):
        with patch("app.shared.llm.providers.openai.ChatOpenAI") as MockChat:
            provider = OpenAIProvider()
            provider.create_model(model="gpt-3.5-turbo", api_key=VALID_KEY_OPENAI)
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_OPENAI,
                model="gpt-3.5-turbo",
                temperature=0
            )

def test_openai_provider_missing_key():
    """Test OpenAIProvider raises error when API key is missing."""
    with patch("app.shared.llm.providers.openai.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = None
        
        provider = OpenAIProvider()
        with pytest.raises(ValueError, match="OPENAI_API_KEY not configured"):
            provider.create_model()

# --- Anthropic Provider Tests ---

def test_anthropic_provider_defaults():
    """Test AnthropicProvider with default settings."""
    with patch("app.shared.llm.providers.anthropic.get_settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY = VALID_KEY_ANTHROPIC
        mock_settings.return_value.CLAUDE_API_KEY = None
        mock_settings.return_value.CLAUDE_MODEL = "claude-3-opus"
        
        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as MockChat:
            provider = AnthropicProvider()
            provider.create_model()
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_ANTHROPIC,
                model="claude-3-opus",
                temperature=0
            )

def test_anthropic_provider_claude_api_key_fallback():
    """Test AnthropicProvider fallback to CLAUDE_API_KEY when ANTHROPIC_API_KEY is unset."""
    with patch("app.shared.llm.providers.anthropic.get_settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY = None
        mock_settings.return_value.CLAUDE_API_KEY = VALID_KEY_ANTHROPIC
        mock_settings.return_value.CLAUDE_MODEL = "claude-3-sonnet"
        
        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as MockChat:
            provider = AnthropicProvider()
            provider.create_model()
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_ANTHROPIC,
                model="claude-3-sonnet",
                temperature=0
            )

def test_anthropic_provider_explicit():
    """Test AnthropicProvider with explicit arguments."""
    with patch("app.shared.llm.providers.anthropic.get_settings"):
        with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as MockChat:
            provider = AnthropicProvider()
            provider.create_model(model="claude-instant-1", api_key=VALID_KEY_ANTHROPIC)
            
            MockChat.assert_called_once_with(
                api_key=VALID_KEY_ANTHROPIC,
                model="claude-instant-1",
                temperature=0
            )

def test_anthropic_provider_missing_key():
    """Test AnthropicProvider raises error when API key is missing."""
    with patch("app.shared.llm.providers.anthropic.get_settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY = None
        mock_settings.return_value.CLAUDE_API_KEY = None
        
        provider = AnthropicProvider()
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
            provider.create_model()
