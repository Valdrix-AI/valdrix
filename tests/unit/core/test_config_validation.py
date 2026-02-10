"""
Tests for app/shared/core/config.py - Configuration management
"""
import pytest
from unittest.mock import patch
from pydantic import ValidationError
from app.shared.core.config import Settings

FAKE_PAYSTACK_SECRET_KEY = "sk_live_TEST_KEY_NOT_REAL_1234567890"
FAKE_PAYSTACK_PUBLIC_KEY = "pk_live_TEST_KEY_NOT_REAL_1234567890"


class TestSettingsValidation:
    """Test settings validation and security checks."""

    def test_settings_missing_required_fields(self):
        """Test validation when required fields are missing."""
        # Ensure no env vars interfere and defaults apply
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.SUPABASE_JWT_SECRET

    def test_settings_invalid_ssl_mode(self):
        """Test validation with invalid SSL mode."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(
                    ENVIRONMENT="production",
                    DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    DEBUG=False,
                    TESTING=False,
                    GROQ_API_KEY="g"*32,
                    DB_SSL_MODE="invalid_mode",
                    _env_file=None
                )
            assert "SECURITY ERROR: DB_SSL_MODE must be 'require', 'verify-ca', or 'verify-full' in production" in str(exc.value)

    def test_settings_production_ssl_require_without_ca(self):
        """Test production SSL requirement without CA certificate."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(
                    ENVIRONMENT="production",
                    DATABASE_URL="postgresql+asyncpg://test",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    DEBUG=False,  # Production mode
                    TESTING=False,
                    DB_SSL_MODE="verify-ca",
                    DB_SSL_CA_CERT_PATH=None,  # Missing CA cert
                    _env_file=None
                )
            
            assert "DB_SSL_CA_CERT_PATH" in str(exc.value)
            assert "mandatory" in str(exc.value)

    def test_settings_production_ssl_verify_ca_success(self):
        """Test successful SSL verification in production."""
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                ENVIRONMENT="production",
                DATABASE_URL="postgresql+asyncpg://test",
                SUPABASE_JWT_SECRET="x"*32,
                ENCRYPTION_KEY="k"*32,
                CSRF_SECRET_KEY="c"*32,
                KDF_SALT="s"*32,
                DEBUG=False,  # Production mode
                TESTING=False,
                DB_SSL_MODE="verify-ca",
                DB_SSL_CA_CERT_PATH="/path/to/ca.crt",
                ADMIN_API_KEY="a"*32,
                GROQ_API_KEY="g"*32,
                PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                _env_file=None
            )
            
            assert settings.DB_SSL_MODE == "verify-ca"
            assert settings.is_production is True

    def test_settings_development_ssl_disable_allowed(self):
        """Test SSL disable allowed in development."""
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                SUPABASE_JWT_SECRET="x"*32,
                ENCRYPTION_KEY="k"*32,
                CSRF_SECRET_KEY="c"*32,
                KDF_SALT="s"*32,
                DEBUG=True,  # Development mode
                DB_SSL_MODE="disable",
                _env_file=None
            )
            
            assert settings.DB_SSL_MODE == "disable"
            assert settings.is_production is False

    def test_settings_admin_api_key_validation(self):
        """Test admin API key validation in production."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(
                    DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    DEBUG=False,  # Production mode
                    ENVIRONMENT="production",
                    TESTING=False,
                    DB_SSL_MODE="require",
                    ADMIN_API_KEY="short",  # Too short
                    GROQ_API_KEY="g"*32,
                    PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                    PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                    _env_file=None
                )
            
            assert "ADMIN_API_KEY" in str(exc.value)
            assert "32 characters" in str(exc.value)

    def test_settings_cors_origins_localhost_warning(self):
        """Test warning for localhost origins in production."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("structlog.get_logger") as mock_logger:
                # Must pass valid prod config to avoid other validation errors
                settings = Settings(
                    DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    DEBUG=False,  # Production mode
                    TESTING=False,
                    ADMIN_API_KEY="a"*32, # Valid API Key
                    ENVIRONMENT="production", # Trigger CORS check
                    API_URL="https://api.example.com",
                    FRONTEND_URL="https://app.example.com",
                    CORS_ORIGINS=["http://localhost:3000", "https://example.com"],
                    GROQ_API_KEY="g"*32,
                    DB_SSL_MODE="require",
                    PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                    PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                    _env_file=None
                )
                
                assert settings.is_production is True
                # Should log warning about localhost in production
                mock_logger.return_value.warning.assert_called()
                # Find the call with "cors_localhost_in_production"
                warning_calls = [args[0] for args, kwargs in mock_logger.return_value.warning.call_args_list]
                assert "cors_localhost_in_production" in warning_calls

    def test_settings_frontend_url_https_warning(self):
        """Test warning for non-HTTPS frontend URL in production."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("structlog.get_logger") as mock_logger:
                settings = Settings(
                    DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    DEBUG=False,  # Production mode
                    TESTING=False,
                    ADMIN_API_KEY="a"*32, # Valid API Key
                    ENVIRONMENT="production",
                    API_URL="https://api.example.com", # Set to HTTPS to isolate frontend warning
                    FRONTEND_URL="http://example.com",  # HTTP instead of HTTPS
                    GROQ_API_KEY="g"*32,
                    DB_SSL_MODE="require",
                    PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                    PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                    _env_file=None
                )
                
                assert settings.is_production is True
                # Should log warning about HTTP in production
                mock_logger.return_value.warning.assert_called()
                warning_calls = [args[0] for args, kwargs in mock_logger.return_value.warning.call_args_list]
                assert "frontend_url_not_https" in warning_calls

    def test_settings_llm_provider_key_missing(self):
        """Test validation when LLM provider is set but key is missing."""
        # Ensure env vars don't provide key and we don't load from .env
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(
                    ENVIRONMENT="production",
                    DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SUPABASE_JWT_SECRET="x"*32,
                    ENCRYPTION_KEY="k"*32,
                    CSRF_SECRET_KEY="c"*32,
                    KDF_SALT="s"*32,
                    LLM_PROVIDER="openai",
                    OPENAI_API_KEY=None,
                    DEBUG=False, # Strict validation in prod
                    TESTING=False,
                    PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                    PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                    _env_file=None # Ignore .env
                )
            
            assert "is missing in production" in str(exc.value)

    def test_settings_llm_provider_key_present(self):
        """Test successful validation when LLM provider key is present."""
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                SUPABASE_JWT_SECRET="x"*32,
                ENCRYPTION_KEY="k"*32,
                CSRF_SECRET_KEY="c"*32,
                KDF_SALT="s"*32,
                LLM_PROVIDER="openai",
                OPENAI_API_KEY="sk-test-key",
                _env_file=None
            )
            
            assert settings.LLM_PROVIDER == "openai"
            assert settings.OPENAI_API_KEY == "sk-test-key"

    def test_settings_is_production_property(self):
        """Test is_production property logic."""
        with patch.dict("os.environ", {}, clear=True):
            # Debug=True should be non-production
            settings_debug = Settings(
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                SUPABASE_JWT_SECRET="x"*32,
                DEBUG=True,
                _env_file=None
            )
            assert settings_debug.is_production is False
            
            # Debug=False should be production
            settings_prod = Settings(
                ENVIRONMENT="production",
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                SUPABASE_JWT_SECRET="x"*32,
                ENCRYPTION_KEY="k"*32, # Required in prod
                CSRF_SECRET_KEY="c"*32, # Required in prod
                KDF_SALT="s"*32, # Required in prod
                DB_SSL_MODE="require",
                ADMIN_API_KEY="a"*32,
                GROQ_API_KEY="g"*32,
                PAYSTACK_SECRET_KEY=FAKE_PAYSTACK_SECRET_KEY,
                PAYSTACK_PUBLIC_KEY=FAKE_PAYSTACK_PUBLIC_KEY,
                DEBUG=False,
                TESTING=False,
                _env_file=None
            )
            assert settings_prod.is_production is True

    def test_settings_default_values(self):
        """Test default values for optional settings."""
        # Use _env_file=None to ignore .env default overrides if any
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                SUPABASE_JWT_SECRET="x"*32,
                ENCRYPTION_KEY="k"*32,
                CSRF_SECRET_KEY="c"*32,
                KDF_SALT="s"*32,
                DB_SSL_MODE="require",
                GROQ_API_KEY="g"*32,
                TESTING=False,
                _env_file=None
            )
            
            # Check default values
            assert settings.LLM_PROVIDER == "groq"
            assert settings.OPENAI_API_KEY is None
            assert settings.CORS_ORIGINS == []
            assert settings.FRONTEND_URL == "http://localhost:5173"
            assert settings.ADMIN_API_KEY is None
