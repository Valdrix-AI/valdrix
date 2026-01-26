import pytest
from app.shared.core.config import Settings

def test_config_production_validation():
    """Verify that production mode requires ENCRYPTION_KEY and API keys."""
    # Mocking production mode by setting DEBUG=False
    invalid_settings = {
        "DEBUG": False,
        "TESTING": False,
        "CSRF_SECRET_KEY": "secure-csrf-key-for-test-validation",
        "ENCRYPTION_KEY": "too-short",
        "DATABASE_URL": "postgresql://test",
        "SUPABASE_JWT_SECRET": "secret",
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "" # Missing
    }
    
    with pytest.raises(ValueError, match="ENCRYPTION_KEY must be at least 32 characters"):
        Settings(**invalid_settings)

def test_config_dev_validation_passes():
    """Verify that dev mode (DEBUG=True) is more lenient."""
    dev_settings = {
        "DEBUG": True,
        "ENCRYPTION_KEY": "short",
        "DATABASE_URL": "postgresql://test",
        "SUPABASE_JWT_SECRET": "secret",
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "" # Missing but in dev
    }
    # Should not raise
    s = Settings(**dev_settings)
    assert s.DEBUG is True
