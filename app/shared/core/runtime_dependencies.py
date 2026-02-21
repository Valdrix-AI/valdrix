"""Runtime dependency validation for production startup."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from importlib.util import find_spec

import structlog

from app.shared.core.config import ENV_PRODUCTION, ENV_STAGING, Settings

logger = structlog.get_logger()


def _module_available(module_name: str) -> bool:
    """Return True when the import target can be resolved."""
    return find_spec(module_name) is not None


def _parse_iso8601_utc(value: str) -> datetime:
    """Parse ISO-8601 and normalize to UTC."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timezone offset required")
    return parsed.astimezone(timezone.utc)


def _validate_prophet_break_glass(settings: Settings, strict_env: bool) -> tuple[str, datetime] | None:
    """
    Validate break-glass metadata for Prophet fallback in strict env.

    Returns:
        tuple(reason, expires_at_utc) when break-glass is active and valid.
        None when break-glass is not active.
    """
    if not strict_env or not settings.FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK:
        return None

    reason = str(settings.FORECASTER_BREAK_GLASS_REASON or "").strip()
    if len(reason) < 10:
        raise RuntimeError(
            "FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true in staging/production "
            "requires FORECASTER_BREAK_GLASS_REASON (min 10 chars)."
        )

    expires_raw = str(settings.FORECASTER_BREAK_GLASS_EXPIRES_AT or "").strip()
    if not expires_raw:
        raise RuntimeError(
            "FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true in staging/production "
            "requires FORECASTER_BREAK_GLASS_EXPIRES_AT (ISO-8601 UTC timestamp)."
        )
    try:
        expires_at = _parse_iso8601_utc(expires_raw)
    except ValueError as exc:
        raise RuntimeError(
            "FORECASTER_BREAK_GLASS_EXPIRES_AT must be a valid ISO-8601 timestamp "
            "with timezone (e.g. 2026-02-22T10:00:00Z)."
        ) from exc

    now_utc = datetime.now(timezone.utc)
    if expires_at <= now_utc:
        raise RuntimeError(
            "FORECASTER_BREAK_GLASS_EXPIRES_AT is in the past. "
            "Renew or disable FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK."
        )

    return reason, expires_at


def validate_runtime_dependencies(settings: Settings) -> None:
    """
    Enforce required runtime dependencies for strict environments.

    Rules:
    - Production/staging: ``tiktoken`` is mandatory for accurate LLM budgeting.
    - Production/staging + SENTRY_DSN configured: ``sentry_sdk`` is mandatory.
    - ``prophet`` remains optional, controlled by fallback policy:
      ``FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK``.
    """
    if settings.TESTING:
        logger.info("runtime_dependency_validation_skipped_testing")
        return

    strict_env = settings.ENVIRONMENT in {ENV_PRODUCTION, ENV_STAGING}
    break_glass = _validate_prophet_break_glass(settings, strict_env)

    if strict_env and not _module_available("tiktoken"):
        raise RuntimeError(
            "Missing required dependency 'tiktoken' in production/staging. "
            "Install tiktoken to ensure accurate LLM token accounting."
        )

    sentry_dsn = str(os.getenv("SENTRY_DSN", "")).strip()
    if strict_env and sentry_dsn and not _module_available("sentry_sdk"):
        raise RuntimeError(
            "SENTRY_DSN is configured but 'sentry_sdk' is not installed. "
            "Install sentry-sdk or unset SENTRY_DSN."
        )

    prophet_available = _module_available("prophet")
    if prophet_available:
        logger.info("prophet_dependency_available")
        return

    if strict_env and not settings.FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK:
        raise RuntimeError(
            "Missing required dependency 'prophet' in production/staging. "
            "Install prophet, or set FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true "
            "as a temporary break-glass override."
        )

    logger.warning(
        "prophet_unavailable_using_holt_winters_fallback",
        environment=settings.ENVIRONMENT,
        strict_env=strict_env,
        break_glass_override=bool(break_glass),
        break_glass_reason=(break_glass[0] if break_glass else None),
        break_glass_expires_at=(
            break_glass[1].isoformat() if break_glass else None
        ),
    )
