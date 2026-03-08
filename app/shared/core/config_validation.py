"""Validation and normalization helpers for application settings."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import os
import sys

import structlog
from app.shared.core.config_validation_runtime import (
    validate_enforcement_guardrails,
    validate_environment_safety,
    validate_integration_config,
    validate_remediation_guardrails,
    validate_turnstile_config,
)


def _is_synthetic_paystack_secret_key(value: str) -> bool:
    return value.startswith("example_paystack_secret_")


def _is_synthetic_paystack_public_key(value: str) -> bool:
    return value.startswith("example_paystack_public_")


def normalize_branding(settings_obj: object) -> None:
    """Normalize legacy product names to canonical Valdrics branding."""
    token = str(getattr(settings_obj, "APP_NAME", "") or "").strip().lower()
    legacy_names = {
        "valdrics",
        "valdrics",
        "valdrics-ai",
        "valdrics",
        "valdrics ai",
    }
    if token in legacy_names:
        structlog.get_logger().warning(
            "legacy_app_name_normalized",
            provided_app_name=getattr(settings_obj, "APP_NAME", None),
            normalized_app_name="Valdrics",
        )
        setattr(settings_obj, "APP_NAME", "Valdrics")


def validate_core_secrets(settings_obj: object) -> None:
    """Validate critical security primitives (CSRF, encryption keys, KDF)."""
    critical_keys = {
        "CSRF_SECRET_KEY": getattr(settings_obj, "CSRF_SECRET_KEY", None),
        "ENCRYPTION_KEY": getattr(settings_obj, "ENCRYPTION_KEY", None),
        "SUPABASE_JWT_SECRET": getattr(settings_obj, "SUPABASE_JWT_SECRET", None),
    }

    for name, value in critical_keys.items():
        if not value or len(value) < 32:
            raise ValueError(f"{name} must be set to a secure value (>= 32 chars).")

    csrf_value = str(getattr(settings_obj, "CSRF_SECRET_KEY", "") or "").strip().lower()
    if csrf_value in {
        "dev_secret_key_change_me_in_prod",
        "change_me",
        "changeme",
        "default",
        "csrf_secret_key",
    }:
        raise ValueError(
            "SECURITY ERROR: CSRF_SECRET_KEY must be set to a non-default secure value."
        )

    kdf_salt = getattr(settings_obj, "KDF_SALT", None)
    if not kdf_salt:
        raise ValueError("KDF_SALT must be set (base64-encoded random 32 bytes).")
    try:
        decoded_salt = base64.b64decode(kdf_salt)
        if len(decoded_salt) != 32:
            raise ValueError("KDF_SALT must decode to exactly 32 bytes.")
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ValueError("KDF_SALT must be valid base64.") from exc

    if getattr(settings_obj, "ENCRYPTION_KEY_CACHE_TTL_SECONDS", 0) < 60:
        raise ValueError("ENCRYPTION_KEY_CACHE_TTL_SECONDS must be >= 60.")
    if getattr(settings_obj, "ENCRYPTION_KEY_CACHE_MAX_SIZE", 0) < 10:
        raise ValueError("ENCRYPTION_KEY_CACHE_MAX_SIZE must be >= 10.")
    if getattr(settings_obj, "BLIND_INDEX_KDF_ITERATIONS", 0) < 10000:
        raise ValueError("BLIND_INDEX_KDF_ITERATIONS must be >= 10000.")


def validate_database_config(settings_obj: object, *, is_production: bool) -> None:
    """Validate database and redis connectivity settings."""
    if is_production:
        if not getattr(settings_obj, "DATABASE_URL", None):
            raise ValueError("DATABASE_URL is required in production.")

        db_ssl_mode = getattr(settings_obj, "DB_SSL_MODE", "")
        if db_ssl_mode not in ["require", "verify-ca", "verify-full"]:
            raise ValueError(
                f"SECURITY ERROR: DB_SSL_MODE must be secure in production (current: {db_ssl_mode})."
            )
        if db_ssl_mode in {"verify-ca", "verify-full"} and not getattr(
            settings_obj, "DB_SSL_CA_CERT_PATH", None
        ):
            raise ValueError(
                "DB_SSL_CA_CERT_PATH is mandatory when DB_SSL_MODE is verify-ca or verify-full in production."
            )
        if getattr(settings_obj, "DB_USE_NULL_POOL", False) and not getattr(
            settings_obj, "DB_EXTERNAL_POOLER", False
        ):
            raise ValueError(
                "DB_USE_NULL_POOL=true requires DB_EXTERNAL_POOLER=true in production."
            )

    if (
        not getattr(settings_obj, "REDIS_URL", None)
        and getattr(settings_obj, "REDIS_HOST", None)
        and getattr(settings_obj, "REDIS_PORT", None)
    ):
        setattr(
            settings_obj,
            "REDIS_URL",
            f"redis://{getattr(settings_obj, 'REDIS_HOST')}:{getattr(settings_obj, 'REDIS_PORT')}",
        )

    if getattr(settings_obj, "DB_SLOW_QUERY_THRESHOLD_SECONDS", 0) <= 0:
        raise ValueError("DB_SLOW_QUERY_THRESHOLD_SECONDS must be > 0.")


def validate_llm_config(settings_obj: object, *, is_production: bool) -> None:
    """Validate LLM provider credentials and abuse guardrail bounds."""
    provider_keys = {
        "openai": getattr(settings_obj, "OPENAI_API_KEY", None),
        "claude": getattr(settings_obj, "CLAUDE_API_KEY", None),
        "anthropic": getattr(settings_obj, "ANTHROPIC_API_KEY", None)
        or getattr(settings_obj, "CLAUDE_API_KEY", None),
        "google": getattr(settings_obj, "GOOGLE_API_KEY", None),
        "groq": getattr(settings_obj, "GROQ_API_KEY", None),
    }

    llm_provider = getattr(settings_obj, "LLM_PROVIDER", None)
    if llm_provider in provider_keys and not provider_keys[llm_provider]:
        if is_production:
            raise ValueError(
                f"LLM_PROVIDER is '{llm_provider}' but its API key is missing."
            )
        structlog.get_logger().info(
            "llm_provider_key_missing_non_prod", provider=llm_provider
        )

    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_PER_MINUTE_CAP", 0) < 1:
        raise ValueError("LLM_GLOBAL_ABUSE_PER_MINUTE_CAP must be >= 1.")
    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_PER_MINUTE_CAP", 0) > 100000:
        raise ValueError("LLM_GLOBAL_ABUSE_PER_MINUTE_CAP must be <= 100000.")
    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD", 0) < 1:
        raise ValueError("LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD must be >= 1.")
    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD", 0) > 10000:
        raise ValueError(
            "LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD must be <= 10000."
        )
    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_BLOCK_SECONDS", 0) < 30:
        raise ValueError("LLM_GLOBAL_ABUSE_BLOCK_SECONDS must be >= 30.")
    if getattr(settings_obj, "LLM_GLOBAL_ABUSE_BLOCK_SECONDS", 0) > 86400:
        raise ValueError("LLM_GLOBAL_ABUSE_BLOCK_SECONDS must be <= 86400.")


def validate_billing_config(settings_obj: object, *, is_production: bool) -> None:
    """Validate Paystack credentials and webhook allowlist configuration."""
    default_currency = str(
        getattr(settings_obj, "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY", "NGN") or "NGN"
    ).strip().upper()
    if default_currency not in {"NGN", "USD"}:
        raise ValueError("PAYSTACK_DEFAULT_CHECKOUT_CURRENCY must be one of: NGN, USD.")

    if is_production:
        paystack_secret = str(getattr(settings_obj, "PAYSTACK_SECRET_KEY", "") or "").strip()
        paystack_public = str(getattr(settings_obj, "PAYSTACK_PUBLIC_KEY", "") or "").strip()
        allow_synthetic = bool(
            getattr(settings_obj, "ALLOW_SYNTHETIC_BILLING_KEYS_FOR_VALIDATION", False)
        )

        if not paystack_secret:
            raise ValueError(
                "PAYSTACK_SECRET_KEY must be a live key (sk_live_...) in production."
            )
        if not paystack_public:
            raise ValueError("PAYSTACK_PUBLIC_KEY is required in production.")
        if allow_synthetic:
            synthetic_validation_context = (
                bool(getattr(settings_obj, "TESTING", False))
                or bool(getattr(settings_obj, "PYTEST_CURRENT_TEST", None))
                or "pytest" in sys.modules
                or str(os.getenv("CI", "") or "").strip().lower() == "true"
            )
            if not synthetic_validation_context:
                raise ValueError(
                    "ALLOW_SYNTHETIC_BILLING_KEYS_FOR_VALIDATION may only be used "
                    "in CI/test validation contexts."
                )
            if not _is_synthetic_paystack_secret_key(paystack_secret):
                raise ValueError(
                    "PAYSTACK_SECRET_KEY must use the synthetic validation format "
                    "example_paystack_secret_* when "
                    "ALLOW_SYNTHETIC_BILLING_KEYS_FOR_VALIDATION=true."
                )
            if not _is_synthetic_paystack_public_key(paystack_public):
                raise ValueError(
                    "PAYSTACK_PUBLIC_KEY must use the synthetic validation format "
                    "example_paystack_public_* when "
                    "ALLOW_SYNTHETIC_BILLING_KEYS_FOR_VALIDATION=true."
                )
        else:
            if not paystack_secret.startswith("sk_live_"):
                raise ValueError(
                    "PAYSTACK_SECRET_KEY must be a live key (sk_live_...) in production."
                )
            if not paystack_public.startswith("pk_live_"):
                raise ValueError(
                    "PAYSTACK_PUBLIC_KEY must be a live key (pk_live_...) in production."
                )
        if default_currency == "USD" and not getattr(
            settings_obj, "PAYSTACK_ENABLE_USD_CHECKOUT", False
        ):
            raise ValueError(
                "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY cannot be USD when PAYSTACK_ENABLE_USD_CHECKOUT is false."
            )

    paystack_webhook_ips = [
        str(value).strip()
        for value in getattr(settings_obj, "PAYSTACK_WEBHOOK_ALLOWED_IPS", [])
        if str(value).strip()
    ]
    if not paystack_webhook_ips:
        raise ValueError("PAYSTACK_WEBHOOK_ALLOWED_IPS must contain at least one IP.")

    for ip_value in paystack_webhook_ips:
        try:
            ipaddress.ip_address(ip_value)
        except ValueError as exc:
            raise ValueError(
                "PAYSTACK_WEBHOOK_ALLOWED_IPS contains invalid IP address: "
                f"{ip_value}"
            ) from exc


def validate_all_config(
    settings_obj: object,
    *,
    env_production: str,
    env_staging: str,
) -> None:
    """Run full multi-domain settings validation pipeline."""
    normalize_branding(settings_obj)

    if bool(getattr(settings_obj, "TESTING", False)) and getattr(
        settings_obj, "ENVIRONMENT", None
    ) in {env_production, env_staging}:
        raise ValueError(
            "TESTING must be false in staging/production runtime environments."
        )

    if bool(getattr(settings_obj, "TESTING", False)):
        return

    is_production = bool(getattr(settings_obj, "is_production", False))
    validate_core_secrets(settings_obj)
    validate_database_config(settings_obj, is_production=is_production)
    validate_llm_config(settings_obj, is_production=is_production)
    validate_billing_config(settings_obj, is_production=is_production)
    validate_integration_config(settings_obj, is_production=is_production)
    validate_observability = getattr(
        settings_obj, "_validate_observability_config", None
    )
    if callable(validate_observability):
        validate_observability()
    validate_turnstile_config(
        settings_obj,
        env_production=env_production,
        env_staging=env_staging,
    )
    validate_remediation_guardrails(
        settings_obj,
        env_production=env_production,
        env_staging=env_staging,
    )
    validate_enforcement_guardrails(settings_obj)
    validate_environment_safety(
        settings_obj,
        env_production=env_production,
        env_staging=env_staging,
    )


__all__ = [
    "normalize_branding",
    "validate_all_config",
    "validate_billing_config",
    "validate_core_secrets",
    "validate_database_config",
    "validate_enforcement_guardrails",
    "validate_environment_safety",
    "validate_integration_config",
    "validate_llm_config",
    "validate_remediation_guardrails",
    "validate_turnstile_config",
]
