import pytest
from unittest.mock import patch
from app.shared.core.config import Settings, get_settings

FAKE_SUPABASE_SECRET = "x" * 32
FAKE_CSRF_SECRET = "c" * 32
FAKE_ENCRYPTION_KEY = "k" * 32
# Base64 for 'KDF_SALT_FOR_TESTING_32_BYTES_OK' (32 bytes)
FAKE_KDF_SALT = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s="
FAKE_PAYSTACK_SECRET_KEY = "sk_live_TEST_KEY_NOT_REAL_1234567890"
FAKE_PAYSTACK_PUBLIC_KEY = "pk_live_TEST_KEY_NOT_REAL_1234567890"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_defaults():
    settings = Settings(
        SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
        DATABASE_URL="postgresql://user:pass@host/db",
        CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
        ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
        KDF_SALT=FAKE_KDF_SALT,
    )
    assert settings.APP_NAME == "Valdrix"
    assert settings.RATELIMIT_ENABLED is True


def test_settings_production_validation():
    # Production without CSRF secret should fail
    # We MUST ensure TESTING=False and DEBUG=False to trigger production validation
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                TESTING=False,
                SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
                DATABASE_URL="postgresql://user:pass@host/db",
                ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
                KDF_SALT=FAKE_KDF_SALT,
                CSRF_SECRET_KEY=None,
            )
        assert "CSRF_SECRET_KEY must be set to a secure value" in str(exc.value)


def test_settings_production_encryption_key_length():
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            TESTING=False,
            SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
            ENCRYPTION_KEY="short",
            KDF_SALT=FAKE_KDF_SALT,
        )
    assert "ENCRYPTION_KEY must be set to a secure value" in str(exc.value)


def test_settings_production_ssl_mode():
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            TESTING=False,
            SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
            ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
            KDF_SALT=FAKE_KDF_SALT,
            DB_SSL_MODE="disable",  # Insecure for prod
        )
    assert "SECURITY ERROR: DB_SSL_MODE must be secure in production" in str(exc.value)


def test_settings_admin_key_env_validation():
    # Staging/Production needs ADMIN_API_KEY
    # We use patch.dict to clear the environment to avoid interference
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc:
            Settings(
                ENVIRONMENT="staging",
                DEBUG=True,  # DEBUG=True doesn't bypass ENV checks for admin key
                SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
                DATABASE_URL="postgresql://host/db",
                CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
                ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
                KDF_SALT=FAKE_KDF_SALT,
                ADMIN_API_KEY=None,  # Force it to None
            )
        assert "ADMIN_API_KEY must be >= 32 chars" in str(exc.value)


def test_settings_rejects_testing_true_in_production() -> None:
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            TESTING=True,
            _env_file=None,
        )
    assert "TESTING must be false in staging/production" in str(exc.value)


def test_settings_rejects_testing_true_in_staging() -> None:
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="staging",
            TESTING=True,
            _env_file=None,
        )
    assert "TESTING must be false in staging/production" in str(exc.value)


def test_settings_llm_provider_key_validation():
    # Set provider but no key
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            TESTING=False,
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
            ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
            KDF_SALT=FAKE_KDF_SALT,
            DB_SSL_MODE="require",  # Correct SSL mode for production
        )
    assert "LLM_PROVIDER is 'openai' but its API key is missing" in str(exc.value)


def test_settings_is_production_property():
    with patch.dict("os.environ", {}, clear=True):
        s_prod = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            TESTING=False,
            SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
            DATABASE_URL="postgresql://host/db",
            CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
            ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
            KDF_SALT=FAKE_KDF_SALT,
            ADMIN_API_KEY="a" * 32,
            GROQ_API_KEY="g" * 32,
            PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
            PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
            REDIS_URL="redis://localhost:6379",
            DB_SSL_MODE="require",
            _env_file=None,
        )
        assert s_prod.is_production is True

        s_dev = Settings(
            DEBUG=True,
            TESTING=False,
            SUPABASE_JWT_SECRET=FAKE_SUPABASE_SECRET,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            CSRF_SECRET_KEY=FAKE_CSRF_SECRET,
            ENCRYPTION_KEY=FAKE_ENCRYPTION_KEY,
            KDF_SALT=FAKE_KDF_SALT,
            DB_SSL_MODE="disable",
            _env_file=None,
        )
        assert s_dev.is_production is False
