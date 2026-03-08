"""Runtime-safety configuration validators kept separate from core secrets checks."""

from __future__ import annotations

import ipaddress

import structlog


def validate_turnstile_config(
    settings_obj: object, *, env_production: str, env_staging: str
) -> None:
    """Validate Turnstile anti-bot controls for public/auth surfaces."""
    timeout_seconds = float(getattr(settings_obj, "TURNSTILE_TIMEOUT_SECONDS", 0))
    if timeout_seconds <= 0:
        raise ValueError("TURNSTILE_TIMEOUT_SECONDS must be > 0.")
    if timeout_seconds > 15:
        raise ValueError("TURNSTILE_TIMEOUT_SECONDS must be <= 15.")

    verify_url = str(getattr(settings_obj, "TURNSTILE_VERIFY_URL", "") or "").strip().lower()
    if not verify_url.startswith("https://"):
        raise ValueError("TURNSTILE_VERIFY_URL must use https://.")

    turnstile_required = (
        bool(getattr(settings_obj, "TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT", False))
        or bool(getattr(settings_obj, "TURNSTILE_REQUIRE_SSO_DISCOVERY", False))
        or bool(getattr(settings_obj, "TURNSTILE_REQUIRE_ONBOARD", False))
    )

    environment = getattr(settings_obj, "ENVIRONMENT", "")
    if (
        bool(getattr(settings_obj, "TURNSTILE_ENABLED", False))
        and turnstile_required
        and environment in {env_production, env_staging}
    ):
        secret = str(getattr(settings_obj, "TURNSTILE_SECRET_KEY", "") or "").strip()
        if len(secret) < 16:
            raise ValueError(
                "TURNSTILE_SECRET_KEY must be configured when Turnstile is enabled in staging/production."
            )
        if bool(getattr(settings_obj, "TURNSTILE_FAIL_OPEN", False)):
            raise ValueError("TURNSTILE_FAIL_OPEN must be false in staging/production.")


def validate_integration_config(settings_obj: object, *, is_production: bool) -> None:
    """Validate SaaS integration strict mode constraints."""
    if bool(getattr(settings_obj, "SAAS_STRICT_INTEGRATIONS", False)):
        sconf = [
            getattr(settings_obj, "SLACK_CHANNEL_ID", None),
            getattr(settings_obj, "JIRA_BASE_URL", None),
            getattr(settings_obj, "GITHUB_ACTIONS_TOKEN", None),
        ]
        if any(sconf) and is_production:
            raise ValueError(
                "SAAS_STRICT_INTEGRATIONS forbids env-based settings in production."
            )


def validate_environment_safety(
    settings_obj: object,
    *,
    env_production: str,
    env_staging: str,
) -> None:
    """Validate network/deployment safety requirements and warnings."""
    trusted_proxy_hops = int(getattr(settings_obj, "TRUSTED_PROXY_HOPS", 0))
    if trusted_proxy_hops < 1 or trusted_proxy_hops > 5:
        raise ValueError("TRUSTED_PROXY_HOPS must be between 1 and 5.")

    trusted_proxy_cidrs = [
        str(cidr).strip()
        for cidr in getattr(settings_obj, "TRUSTED_PROXY_CIDRS", [])
        if str(cidr).strip()
    ]
    for cidr in trusted_proxy_cidrs:
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"TRUSTED_PROXY_CIDRS contains invalid CIDR: {cidr}") from exc

    environment = getattr(settings_obj, "ENVIRONMENT", "")
    if (
        bool(getattr(settings_obj, "TRUST_PROXY_HEADERS", False))
        and environment in {env_production, env_staging}
        and not trusted_proxy_cidrs
    ):
        raise ValueError(
            "TRUSTED_PROXY_CIDRS must be configured when TRUST_PROXY_HEADERS=true in staging/production."
        )

    if bool(getattr(settings_obj, "is_production", False)) or environment == env_staging:
        admin_api_key = getattr(settings_obj, "ADMIN_API_KEY", None)
        if not admin_api_key or len(str(admin_api_key)) < 32:
            raise ValueError("ADMIN_API_KEY must be >= 32 chars in staging/production.")

        web_concurrency_raw = str(
            getattr(settings_obj, "WEB_CONCURRENCY", 1) or 1
        ).strip()
        try:
            web_concurrency = int(web_concurrency_raw)
        except (TypeError, ValueError):
            web_concurrency = 1

        if web_concurrency > 1 and (
            not bool(getattr(settings_obj, "CIRCUIT_BREAKER_DISTRIBUTED_STATE", False))
            or not getattr(settings_obj, "REDIS_URL", None)
        ):
            raise ValueError(
                "WEB_CONCURRENCY > 1 requires CIRCUIT_BREAKER_DISTRIBUTED_STATE=true "
                "and REDIS_URL configured in staging/production."
            )

        if (
            bool(getattr(settings_obj, "RATELIMIT_ENABLED", False))
            and not getattr(settings_obj, "REDIS_URL", None)
            and not bool(getattr(settings_obj, "ALLOW_IN_MEMORY_RATE_LIMITS", False))
        ):
            raise ValueError(
                "REDIS_URL is required for distributed rate limiting in "
                "staging/production. Set ALLOW_IN_MEMORY_RATE_LIMITS=true only "
                "for temporary break-glass usage."
            )

        logger = structlog.get_logger()
        cors_origins = getattr(settings_obj, "CORS_ORIGINS", [])
        if any("localhost" in o or "127.0.0.1" in o for o in cors_origins):
            logger.warning("cors_localhost_in_production")

        for url in [getattr(settings_obj, "API_URL", None), getattr(settings_obj, "FRONTEND_URL", None)]:
            if url and str(url).startswith("http://"):
                logger.warning("insecure_url_in_production", url=url)


def validate_remediation_guardrails(
    settings_obj: object,
    *,
    env_production: str,
    env_staging: str,
) -> None:
    """Validate safety guardrail configuration for remediation execution."""
    normalized_scope = str(
        getattr(settings_obj, "REMEDIATION_KILL_SWITCH_SCOPE", "tenant") or "tenant"
    ).strip().lower()
    if normalized_scope not in {"tenant", "global"}:
        raise ValueError("REMEDIATION_KILL_SWITCH_SCOPE must be one of: tenant, global.")
    setattr(settings_obj, "REMEDIATION_KILL_SWITCH_SCOPE", normalized_scope)

    if (
        getattr(settings_obj, "ENVIRONMENT", "") in {env_production, env_staging}
        and normalized_scope == "global"
        and not bool(
            getattr(settings_obj, "REMEDIATION_KILL_SWITCH_ALLOW_GLOBAL_SCOPE", False)
        )
    ):
        raise ValueError(
            "REMEDIATION_KILL_SWITCH_SCOPE=global requires "
            "REMEDIATION_KILL_SWITCH_ALLOW_GLOBAL_SCOPE=true in staging/production."
        )


def validate_enforcement_guardrails(settings_obj: object) -> None:
    """Validate enforcement gate runtime safety controls."""
    if getattr(settings_obj, "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 0) <= 0:
        raise ValueError("ENFORCEMENT_GATE_TIMEOUT_SECONDS must be > 0.")
    if getattr(settings_obj, "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 0) > 30:
        raise ValueError("ENFORCEMENT_GATE_TIMEOUT_SECONDS must be <= 30.")
    if getattr(settings_obj, "ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP", 0) < 1:
        raise ValueError("ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP must be >= 1.")
    if getattr(settings_obj, "ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP", 0) > 100000:
        raise ValueError("ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP must be <= 100000.")

    export_signing_secret = str(
        getattr(settings_obj, "ENFORCEMENT_EXPORT_SIGNING_SECRET", "") or ""
    ).strip()
    if export_signing_secret and len(export_signing_secret) < 32:
        raise ValueError(
            "ENFORCEMENT_EXPORT_SIGNING_SECRET must be >= 32 chars when provided."
        )

    export_signing_kid = str(
        getattr(settings_obj, "ENFORCEMENT_EXPORT_SIGNING_KID", "") or ""
    ).strip()
    if export_signing_kid and len(export_signing_kid) > 64:
        raise ValueError("ENFORCEMENT_EXPORT_SIGNING_KID must be <= 64 chars.")

    if getattr(settings_obj, "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS", 0) < 60:
        raise ValueError(
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS must be >= 60."
        )
    if getattr(settings_obj, "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS", 0) > 604800:
        raise ValueError(
            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS must be <= 604800."
        )
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES", 0) < 1:
        raise ValueError("ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES must be >= 1.")
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES", 0) > 1000:
        raise ValueError(
            "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES must be <= 1000."
        )
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT", 0) < 1:
        raise ValueError(
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT must be >= 1."
        )
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT", 0) > 1000:
        raise ValueError(
            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT must be <= 1000."
        )
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD", 0) < 0:
        raise ValueError(
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD must be >= 0."
        )
    if getattr(settings_obj, "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT", 0) < 1:
        raise ValueError(
            "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT must be >= 1."
        )
    if getattr(settings_obj, "ENFORCEMENT_EXPORT_MAX_DAYS", 0) < 1:
        raise ValueError("ENFORCEMENT_EXPORT_MAX_DAYS must be >= 1.")
    if getattr(settings_obj, "ENFORCEMENT_EXPORT_MAX_DAYS", 0) > 3650:
        raise ValueError("ENFORCEMENT_EXPORT_MAX_DAYS must be <= 3650.")
    if getattr(settings_obj, "ENFORCEMENT_EXPORT_MAX_ROWS", 0) < 1:
        raise ValueError("ENFORCEMENT_EXPORT_MAX_ROWS must be >= 1.")
    if getattr(settings_obj, "ENFORCEMENT_EXPORT_MAX_ROWS", 0) > 50000:
        raise ValueError("ENFORCEMENT_EXPORT_MAX_ROWS must be <= 50000.")

    fallback_signing_keys = list(
        getattr(settings_obj, "ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS", []) or []
    )
    if len(fallback_signing_keys) > 5:
        raise ValueError(
            "ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS must contain at most 5 keys."
        )
    for fallback_secret in fallback_signing_keys:
        if len(str(fallback_secret or "").strip()) < 32:
            raise ValueError(
                "Each ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS key must be >= 32 chars."
            )

