import pytest
from typing import Dict
from unittest.mock import MagicMock, patch
from app.shared.llm.factory import LLMFactory, AnalysisComplexity

# Patch modules before they are used (if needed by underlying imports)
# However, usually patch.dict(sys.modules) is safer or putting them in a fixture works better 
# but if the import itself requires them, we must patch BEFORE import.
# But 'from app.shared.llm.factory' is the top level import.
# Let's try to mock them via sys.modules but after the import statement
# if the import statement doesn't trigger the usage.
# If `app.shared.llm.factory` imports pandas at top level, we might have issues.
# Let's assume we can move the mock setup to a fixture or try `patch.dict`.

# Re-structuring to standards compliant:

@pytest.fixture
def mock_settings():
    with patch("app.shared.llm.factory.get_settings") as mock:
        yield mock

def test_validate_api_key_success():
    # Should not raise
    LLMFactory.validate_api_key("openai", "sk-12345678901234567890")

def test_validate_api_key_missing():
    with pytest.raises(ValueError) as exc:
        LLMFactory.validate_api_key("openai", None)
    assert "not configured" in str(exc.value)

def test_validate_api_key_placeholder():
    with pytest.raises(ValueError) as exc:
        LLMFactory.validate_api_key("openai", "sk-xxx-placeholder")
    assert "contains a placeholder" in str(exc.value)

def test_validate_api_key_too_short():
    with pytest.raises(ValueError) as exc:
        LLMFactory.validate_api_key("openai", "sk-short")
    assert "too short" in str(exc.value)

def test_estimate_tokens():
    assert LLMFactory.estimate_tokens("abcd") == 1
    assert LLMFactory.estimate_tokens("abcdefgh") == 2
    assert LLMFactory.estimate_tokens("") == 0

def test_classify_complexity():
    assert LLMFactory.classify_complexity(500) == AnalysisComplexity.SIMPLE
    assert LLMFactory.classify_complexity(2000) == AnalysisComplexity.MEDIUM
    assert LLMFactory.classify_complexity(5000) == AnalysisComplexity.COMPLEX

def test_select_provider_byok(mock_settings):
    mock_settings.return_value.GROQ_API_KEY = "key"
    prov, comp = LLMFactory.select_provider("text", tenant_byok_provider="openai")
    assert prov == "openai"
    assert comp == AnalysisComplexity.MEDIUM

def test_select_provider_waterfall_simple(mock_settings):
    mock_settings.return_value.GROQ_API_KEY = "gsk-..."
    # SIMPLE => Groq preferred
    prov, _ = LLMFactory.select_provider("a" * 400) # 100 tokens
    assert prov == "groq"

def test_select_provider_waterfall_medium(mock_settings):
    mock_settings.return_value.GROQ_API_KEY = None
    mock_settings.return_value.GOOGLE_API_KEY = "g-key"
    # MEDIUM => Google preferred if Groq missing
    prov, _ = LLMFactory.select_provider("a" * 8000) # 2000 tokens
    assert prov == "google"

def test_select_provider_waterfall_complex(mock_settings):
    mock_settings.return_value.OPENAI_API_KEY = "sk-..."
    # COMPLEX => OpenAI preferred
    prov, _ = LLMFactory.select_provider("a" * 20000) # 5000 tokens
    assert prov == "openai"

def test_estimate_cost():
    # OpenAI default: input $0.15, output $0.60 per 1M (example)
    # Price is 0 if provider or default pricing is missing.
    with patch("app.shared.llm.factory.LLM_PRICING", {"openai": {"default": MagicMock(input=0.15, output=0.60)}}):
        cost = LLMFactory.estimate_cost("openai", 1_000_000, 1_000_000)
        assert cost == 0.75
    
    assert LLMFactory.estimate_cost("unknown", 100, 100) == 0.0

def test_create_all_providers(mock_settings):
    mock_settings.return_value.LLM_PROVIDER = "groq"
    
    with patch("app.shared.llm.providers.OpenAIProvider.create_model") as m1:
        LLMFactory.create("openai")
        assert m1.called
        
    with patch("app.shared.llm.providers.AnthropicProvider.create_model") as m2:
        LLMFactory.create("anthropic")
        assert m2.called
        
    with patch("app.shared.llm.providers.GoogleProvider.create_model") as m3:
        LLMFactory.create("google")
        assert m3.called
        
    with patch("app.shared.llm.providers.GroqProvider.create_model") as m4:
        LLMFactory.create("groq")
        assert m4.called

def test_create_unsupported():
    with pytest.raises(ValueError) as exc:
        LLMFactory.create("bad-provider")
    assert "Unsupported provider" in str(exc.value)

def test_create_smart(mock_settings):
    mock_settings.return_value.GROQ_API_KEY = "key"
    with patch("app.shared.llm.providers.GroqProvider.create_model", return_value=MagicMock()) as mock_create:
        llm, prov, comp = LLMFactory.create_smart("short text")
        assert prov == "groq"
        assert comp == AnalysisComplexity.SIMPLE
        assert mock_create.called
