import pytest
from unittest.mock import patch
from app.shared.core.config import Settings, get_settings

@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_defaults():
    settings = Settings(SUPABASE_JWT_SECRET="x"*32, DATABASE_URL="postgresql://user:pass@host/db")
    assert settings.APP_NAME == "Valdrix"
    assert settings.RATELIMIT_ENABLED is True

def test_settings_production_validation():
    # Production without CSRF secret should fail
    # We MUST ensure TESTING=False and DEBUG=False to trigger production validation
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc:
            Settings(
                DEBUG=False, 
                TESTING=False,
                SUPABASE_JWT_SECRET="x"*32,
                DATABASE_URL="postgresql://user:pass@host/db",
                ENCRYPTION_KEY="k"*32,
                KDF_SALT="s"*32,
                CSRF_SECRET_KEY=None,
            )
        assert "CSRF_SECRET_KEY must be set" in str(exc.value)





def test_settings_production_encryption_key_length():
    with pytest.raises(ValueError) as exc:
        Settings(
            DEBUG=False,
            TESTING=False,
            SUPABASE_JWT_SECRET="x"*32,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY="c"*32,
            ENCRYPTION_KEY="short",
            KDF_SALT="s"*32,
        )
    assert "ENCRYPTION_KEY must be at least 32" in str(exc.value)

def test_settings_production_ssl_mode():
    with pytest.raises(ValueError) as exc:
        Settings(
            DEBUG=False,
            TESTING=False,
            SUPABASE_JWT_SECRET="x"*32,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY="c"*32,
            ENCRYPTION_KEY="k"*32,
            KDF_SALT="s"*32,
            DB_SSL_MODE="disable" # Insecure for prod
        )
    assert "DB_SSL_MODE must be 'require'" in str(exc.value)

def test_settings_admin_key_env_validation():
    # Staging/Production needs ADMIN_API_KEY
    # We use patch.dict to clear the environment to avoid interference
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc:
            Settings(
                ENVIRONMENT="staging",
                DEBUG=True, # DEBUG=True doesn't bypass ENV checks for admin key
                SUPABASE_JWT_SECRET="x"*32,
                DATABASE_URL="postgresql://host/db",
                ADMIN_API_KEY=None # Force it to None
            )
        assert "ADMIN_API_KEY must be configured" in str(exc.value)

def test_settings_llm_provider_key_validation():
    # Set provider but no key
    with pytest.raises(ValueError) as exc:
        Settings(
            DEBUG=False,
            TESTING=False,
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            SUPABASE_JWT_SECRET="x"*32,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY="c"*32,
            ENCRYPTION_KEY="k"*32,
            KDF_SALT="s"*32,
            DB_SSL_MODE="disable"  # Add SSL mode for testing
        )
    assert "SECURITY ERROR" in str(exc.value)

def test_settings_is_production_property():
    s_prod = Settings(DEBUG=False, SUPABASE_JWT_SECRET="x", DATABASE_URL="x")
    assert s_prod.is_production is True
    
    s_dev = Settings(DEBUG=True, SUPABASE_JWT_SECRET="x", DATABASE_URL="x")
    assert s_dev.is_production is False
