from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest

from app.shared.core.config import (
    ENV_DEVELOPMENT,
    ENV_PRODUCTION,
    ENV_STAGING,
    Settings,
    reload_settings_from_environment,
)


FAKE_SUPABASE_SECRET = "x" * 32
FAKE_CSRF_SECRET = "c" * 32
FAKE_ENCRYPTION_KEY = "k" * 32
FAKE_KDF_SALT = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s="


def _settings() -> Settings:
    s = Settings(TESTING=True, _env_file=None)
    s.ENVIRONMENT = ENV_DEVELOPMENT
    s.CSRF_SECRET_KEY = FAKE_CSRF_SECRET
    s.ENCRYPTION_KEY = FAKE_ENCRYPTION_KEY
    s.SUPABASE_JWT_SECRET = FAKE_SUPABASE_SECRET
    s.KDF_SALT = FAKE_KDF_SALT
    s.ENCRYPTION_KEY_CACHE_TTL_SECONDS = 3600
    s.ENCRYPTION_KEY_CACHE_MAX_SIZE = 1000
    s.BLIND_INDEX_KDF_ITERATIONS = 50000
    s.DB_SLOW_QUERY_THRESHOLD_SECONDS = 0.2
    s.DB_SSL_MODE = "require"
    s.DB_SSL_CA_CERT_PATH = None
    s.DB_USE_NULL_POOL = False
    s.DB_EXTERNAL_POOLER = False
    s.LLM_PROVIDER = "groq"
    s.GROQ_API_KEY = "g" * 32
    s.PAYSTACK_DEFAULT_CHECKOUT_CURRENCY = "NGN"
    s.PAYSTACK_ENABLE_USD_CHECKOUT = False
    s.TURNSTILE_VERIFY_URL = "https://example.com/verify"
    s.TURNSTILE_TIMEOUT_SECONDS = 3.0
    s.TURNSTILE_ENABLED = False
    s.TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT = True
    s.TURNSTILE_REQUIRE_SSO_DISCOVERY = True
    s.TURNSTILE_REQUIRE_ONBOARD = True
    s.TRUST_PROXY_HEADERS = False
    s.TRUSTED_PROXY_HOPS = 1
    s.TRUSTED_PROXY_CIDRS = []
    s.ADMIN_API_KEY = "a" * 32
    s.CIRCUIT_BREAKER_DISTRIBUTED_STATE = True
    s.REDIS_URL = "redis://localhost:6379"
    s.RATELIMIT_ENABLED = True
    s.ALLOW_IN_MEMORY_RATE_LIMITS = False
    s.CORS_ORIGINS = []
    s.API_URL = "https://api.example.com"
    s.FRONTEND_URL = "https://app.example.com"
    s.REMEDIATION_KILL_SWITCH_SCOPE = "tenant"
    s.REMEDIATION_KILL_SWITCH_ALLOW_GLOBAL_SCOPE = False
    s.ENFORCEMENT_GATE_TIMEOUT_SECONDS = 2.0
    s.ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP = 1200
    s.ENFORCEMENT_EXPORT_SIGNING_SECRET = None
    s.ENFORCEMENT_EXPORT_SIGNING_KID = "kid"
    s.ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS = 86400
    s.ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES = 500
    s.ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT = 200
    s.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD = 100.0
    s.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT = 5
    s.ENFORCEMENT_EXPORT_MAX_DAYS = 366
    s.ENFORCEMENT_EXPORT_MAX_ROWS = 10000
    s.ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS = []
    return s


def test_reload_settings_from_environment_success_and_cache_warm() -> None:
    refreshed = object()
    get_settings_mock = MagicMock(return_value=refreshed)
    get_settings_mock.cache_clear = MagicMock()
    logger = MagicMock()

    fake_security_module = types.ModuleType("app.shared.core.security")

    class _KeyManager:
        clear_key_caches = MagicMock()

    fake_security_module.EncryptionKeyManager = _KeyManager

    with (
        patch("app.shared.core.config.get_settings", get_settings_mock),
        patch("app.shared.core.config.structlog.get_logger", return_value=logger),
        patch.dict("sys.modules", {"app.shared.core.security": fake_security_module}),
    ):
        result = reload_settings_from_environment()

    assert result is refreshed
    get_settings_mock.cache_clear.assert_called_once()
    _KeyManager.clear_key_caches.assert_called_once_with(warm=True)
    logger.info.assert_any_call("settings_reload_started")
    logger.info.assert_any_call("settings_reload_completed")


def test_reload_settings_from_environment_logs_warning_when_cache_refresh_fails() -> None:
    refreshed = object()
    get_settings_mock = MagicMock(return_value=refreshed)
    get_settings_mock.cache_clear = MagicMock()
    logger = MagicMock()

    fake_security_module = types.ModuleType("app.shared.core.security")

    class _KeyManager:
        @staticmethod
        def clear_key_caches(*, warm: bool) -> None:
            del warm
            raise RuntimeError("cache warm failure")

    fake_security_module.EncryptionKeyManager = _KeyManager

    with (
        patch("app.shared.core.config.get_settings", get_settings_mock),
        patch("app.shared.core.config.structlog.get_logger", return_value=logger),
        patch.dict("sys.modules", {"app.shared.core.security": fake_security_module}),
    ):
        result = reload_settings_from_environment()

    assert result is refreshed
    logger.warning.assert_called_once()


def test_config_core_secret_validator_branch_paths() -> None:
    s = _settings()

    s.KDF_SALT = None
    with pytest.raises(ValueError, match="KDF_SALT must be set"):
        s._validate_core_secrets()

    s = _settings()
    s.KDF_SALT = "YQ=="  # valid base64, wrong decoded length
    with pytest.raises(ValueError, match="KDF_SALT must be valid base64"):
        s._validate_core_secrets()

    s = _settings()
    s.ENCRYPTION_KEY_CACHE_TTL_SECONDS = 59
    with pytest.raises(ValueError, match="ENCRYPTION_KEY_CACHE_TTL_SECONDS must be >= 60"):
        s._validate_core_secrets()

    s = _settings()
    s.ENCRYPTION_KEY_CACHE_MAX_SIZE = 9
    with pytest.raises(ValueError, match="ENCRYPTION_KEY_CACHE_MAX_SIZE must be >= 10"):
        s._validate_core_secrets()


def test_config_database_validator_branch_paths() -> None:
    s = _settings()
    s.ENVIRONMENT = ENV_PRODUCTION
    s.DATABASE_URL = None
    with pytest.raises(ValueError, match="DATABASE_URL is required in production"):
        s._validate_database_config()

    s = _settings()
    s.DB_SLOW_QUERY_THRESHOLD_SECONDS = 0
    with pytest.raises(ValueError, match="DB_SLOW_QUERY_THRESHOLD_SECONDS must be > 0"):
        s._validate_database_config()


@pytest.mark.parametrize(
    ("field_name", "value", "expected"),
    [
        ("LLM_GLOBAL_ABUSE_PER_MINUTE_CAP", 0, "LLM_GLOBAL_ABUSE_PER_MINUTE_CAP must be >= 1"),
        ("LLM_GLOBAL_ABUSE_PER_MINUTE_CAP", 100001, "LLM_GLOBAL_ABUSE_PER_MINUTE_CAP must be <= 100000"),
        (
            "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD",
            0,
            "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD must be >= 1",
        ),
        (
            "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD",
            10001,
            "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD must be <= 10000",
        ),
        ("LLM_GLOBAL_ABUSE_BLOCK_SECONDS", 29, "LLM_GLOBAL_ABUSE_BLOCK_SECONDS must be >= 30"),
        ("LLM_GLOBAL_ABUSE_BLOCK_SECONDS", 86401, "LLM_GLOBAL_ABUSE_BLOCK_SECONDS must be <= 86400"),
    ],
)
def test_config_llm_guardrail_bounds(field_name: str, value: int, expected: str) -> None:
    s = _settings()
    setattr(s, field_name, value)
    with pytest.raises(ValueError, match=expected):
        s._validate_llm_config()


def test_config_billing_validator_branch_paths() -> None:
    s = _settings()
    s.PAYSTACK_DEFAULT_CHECKOUT_CURRENCY = "EUR"
    with pytest.raises(ValueError, match="PAYSTACK_DEFAULT_CHECKOUT_CURRENCY"):
        s._validate_billing_config()

    s = _settings()
    s.ENVIRONMENT = ENV_PRODUCTION
    s.PAYSTACK_SECRET_KEY = "sk_test_bad"
    s.PAYSTACK_PUBLIC_KEY = "pk_live_x"
    with pytest.raises(ValueError, match="PAYSTACK_SECRET_KEY must be a live key"):
        s._validate_billing_config()

    s = _settings()
    s.ENVIRONMENT = ENV_PRODUCTION
    s.PAYSTACK_SECRET_KEY = "sk_live_good"
    s.PAYSTACK_PUBLIC_KEY = None
    with pytest.raises(ValueError, match="PAYSTACK_PUBLIC_KEY is required"):
        s._validate_billing_config()

    s = _settings()
    s.ENVIRONMENT = ENV_PRODUCTION
    s.PAYSTACK_SECRET_KEY = "sk_live_good"
    s.PAYSTACK_PUBLIC_KEY = "pk_live_good"
    s.PAYSTACK_DEFAULT_CHECKOUT_CURRENCY = "USD"
    s.PAYSTACK_ENABLE_USD_CHECKOUT = False
    with pytest.raises(ValueError, match="cannot be USD"):
        s._validate_billing_config()

    s = _settings()
    s.PAYSTACK_WEBHOOK_ALLOWED_IPS = []
    with pytest.raises(ValueError, match="PAYSTACK_WEBHOOK_ALLOWED_IPS must contain at least one IP"):
        s._validate_billing_config()

    s = _settings()
    s.PAYSTACK_WEBHOOK_ALLOWED_IPS = ["bad-ip"]
    with pytest.raises(ValueError, match="PAYSTACK_WEBHOOK_ALLOWED_IPS contains invalid IP address"):
        s._validate_billing_config()


def test_config_turnstile_validator_branch_paths() -> None:
    s = _settings()
    s.TURNSTILE_TIMEOUT_SECONDS = 0
    with pytest.raises(ValueError, match="TURNSTILE_TIMEOUT_SECONDS must be > 0"):
        s._validate_turnstile_config()

    s = _settings()
    s.TURNSTILE_TIMEOUT_SECONDS = 16
    with pytest.raises(ValueError, match="TURNSTILE_TIMEOUT_SECONDS must be <= 15"):
        s._validate_turnstile_config()

    s = _settings()
    s.TURNSTILE_VERIFY_URL = "http://insecure.example.com/verify"
    with pytest.raises(ValueError, match="TURNSTILE_VERIFY_URL must use https://"):
        s._validate_turnstile_config()

    s = _settings()
    s.ENVIRONMENT = ENV_STAGING
    s.TURNSTILE_ENABLED = True
    s.TURNSTILE_SECRET_KEY = "short"
    with pytest.raises(ValueError, match="TURNSTILE_SECRET_KEY must be configured"):
        s._validate_turnstile_config()

    s = _settings()
    s.ENVIRONMENT = ENV_STAGING
    s.TURNSTILE_ENABLED = True
    s.TURNSTILE_SECRET_KEY = "x" * 24
    s.TURNSTILE_FAIL_OPEN = True
    with pytest.raises(ValueError, match="TURNSTILE_FAIL_OPEN must be false"):
        s._validate_turnstile_config()

    s = _settings()
    s.ENVIRONMENT = ENV_STAGING
    s.TURNSTILE_ENABLED = True
    s.TURNSTILE_SECRET_KEY = "x" * 24
    s.TURNSTILE_FAIL_OPEN = False
    s._validate_turnstile_config()


def test_config_environment_safety_branch_paths() -> None:
    s = _settings()
    s.TRUSTED_PROXY_HOPS = 0
    with pytest.raises(ValueError, match="TRUSTED_PROXY_HOPS must be between 1 and 5"):
        s._validate_environment_safety()

    s = _settings()
    s.ENVIRONMENT = ENV_STAGING
    s.ADMIN_API_KEY = "a" * 32
    s.REDIS_URL = "redis://localhost:6379"
    s.RATELIMIT_ENABLED = False
    s.CORS_ORIGINS = ["http://localhost:5173"]
    s.API_URL = "http://api.example.com"
    s.FRONTEND_URL = "http://app.example.com"
    with patch("app.shared.core.config.structlog.get_logger") as get_logger:
        with patch.dict(os.environ, {"WEB_CONCURRENCY": "not-an-int"}, clear=False):
            s._validate_environment_safety()
    assert get_logger.return_value.warning.call_count >= 2

    s = _settings()
    s.TRUSTED_PROXY_CIDRS = ["not-a-cidr"]
    with pytest.raises(ValueError, match="TRUSTED_PROXY_CIDRS contains invalid CIDR"):
        s._validate_environment_safety()

    s = _settings()
    s.ENVIRONMENT = ENV_PRODUCTION
    s.TRUST_PROXY_HEADERS = True
    s.TRUSTED_PROXY_CIDRS = []
    with pytest.raises(
        ValueError,
        match="TRUSTED_PROXY_CIDRS must be configured when TRUST_PROXY_HEADERS=true",
    ):
        s._validate_environment_safety()


@pytest.mark.parametrize(
    ("field_name", "value", "expected"),
    [
        ("ENFORCEMENT_GATE_TIMEOUT_SECONDS", 0, "ENFORCEMENT_GATE_TIMEOUT_SECONDS must be > 0"),
        ("ENFORCEMENT_GATE_TIMEOUT_SECONDS", 31, "ENFORCEMENT_GATE_TIMEOUT_SECONDS must be <= 30"),
        (
            "ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP",
            100001,
            "ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP must be <= 100000",
        ),
        ("ENFORCEMENT_EXPORT_SIGNING_KID", "k" * 65, "ENFORCEMENT_EXPORT_SIGNING_KID must be <= 64"),
        (
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS",
            59,
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS must be >= 60",
        ),
        (
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS",
            604801,
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS must be <= 604800",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES",
            0,
            "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES must be >= 1",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES",
            1001,
            "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES must be <= 1000",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT",
            0,
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT must be >= 1",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT",
            1001,
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT must be <= 1000",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD",
            -0.01,
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD must be >= 0",
        ),
        (
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT",
            0,
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT must be >= 1",
        ),
        ("ENFORCEMENT_EXPORT_MAX_DAYS", 0, "ENFORCEMENT_EXPORT_MAX_DAYS must be >= 1"),
        ("ENFORCEMENT_EXPORT_MAX_DAYS", 3651, "ENFORCEMENT_EXPORT_MAX_DAYS must be <= 3650"),
        ("ENFORCEMENT_EXPORT_MAX_ROWS", 0, "ENFORCEMENT_EXPORT_MAX_ROWS must be >= 1"),
        ("ENFORCEMENT_EXPORT_MAX_ROWS", 50001, "ENFORCEMENT_EXPORT_MAX_ROWS must be <= 50000"),
    ],
)
def test_config_enforcement_guardrail_bounds(field_name: str, value: object, expected: str) -> None:
    s = _settings()
    setattr(s, field_name, value)
    with pytest.raises(ValueError, match=expected):
        s._validate_enforcement_guardrails()


def test_config_enforcement_guardrails_rejects_too_many_fallback_signing_keys() -> None:
    s = _settings()
    s.ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS = ["x" * 32] * 6
    with pytest.raises(ValueError, match="at most 5 keys"):
        s._validate_enforcement_guardrails()
