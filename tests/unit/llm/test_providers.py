import pytest
from unittest.mock import patch, MagicMock
from app.shared.llm.providers.anthropic import AnthropicProvider
from app.shared.llm.providers.google import GoogleProvider
from app.shared.llm.providers.groq import GroqProvider

@pytest.fixture
def mock_settings():
    # We need to mock get_settings in each provider module
    with patch("app.shared.llm.providers.anthropic.get_settings") as m1, \
         patch("app.shared.llm.providers.google.get_settings") as m2, \
         patch("app.shared.llm.providers.groq.get_settings") as m3:
        
        settings = MagicMock()
        settings.ANTHROPIC_API_KEY = "sk-ant-" + "x" * 20
        settings.CLAUDE_MODEL = "claude-3"
        settings.GOOGLE_API_KEY = "google-" + "x" * 20
        settings.GOOGLE_MODEL = "gemini-pro"
        settings.GROQ_API_KEY = "groq-" + "x" * 20
        settings.GROQ_MODEL = "llama3-70b"
        
        m1.return_value = settings
        m2.return_value = settings
        m3.return_value = settings
        yield settings

def test_anthropic_provider_creation(mock_settings):
    provider = AnthropicProvider()
    with patch("app.shared.llm.providers.anthropic.ChatAnthropic") as mock_chat:
        provider.create_model()
        mock_chat.assert_called_once_with(
            api_key=mock_settings.ANTHROPIC_API_KEY,
            model="claude-3",
            temperature=0
        )

def test_google_provider_creation(mock_settings):
    provider = GoogleProvider()
    with patch("app.shared.llm.providers.google.ChatGoogleGenerativeAI") as mock_chat:
        provider.create_model()
        mock_chat.assert_called_once_with(
            google_api_key=mock_settings.GOOGLE_API_KEY,
            model="gemini-pro",
            temperature=0
        )

def test_groq_provider_creation(mock_settings):
    provider = GroqProvider()
    with patch("app.shared.llm.providers.groq.ChatGroq") as mock_chat:
        provider.create_model()
        mock_chat.assert_called_once_with(
            api_key=mock_settings.GROQ_API_KEY,
            model="llama3-70b",
            temperature=0
        )

def test_provider_missing_key_raises(mock_settings):
    mock_settings.ANTHROPIC_API_KEY = None
    mock_settings.CLAUDE_API_KEY = None
    provider = AnthropicProvider()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
        provider.create_model()
