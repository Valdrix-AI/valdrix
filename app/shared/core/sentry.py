"""
Sentry Integration for Error Tracking

Provides production error tracking with:
- Automatic exception capture
- Performance monitoring
- Trace ID correlation
- Environment filtering

Usage:
    # Called automatically in app startup
    init_sentry()

    # Optional: Manually capture
    import sentry_sdk
    sentry_sdk.capture_exception(error)
"""

import os
from typing import Any

import structlog

logger = structlog.get_logger()

# Optional import - resolved once at module import, but only enforced when DSN is set.
SENTRY_IMPORT_ERROR: str | None = None
SENTRY_AVAILABLE = False
sentry_sdk: Any | None = None
FastApiIntegration: Any | None = None
SqlalchemyIntegration: Any | None = None
LoggingIntegration: Any | None = None

try:
    import sentry_sdk as _sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration as _FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import (
        SqlalchemyIntegration as _SqlalchemyIntegration,
    )
    from sentry_sdk.integrations.logging import LoggingIntegration as _LoggingIntegration

    sentry_sdk = _sentry_sdk
    FastApiIntegration = _FastApiIntegration
    SqlalchemyIntegration = _SqlalchemyIntegration
    LoggingIntegration = _LoggingIntegration

    SENTRY_AVAILABLE = True
except ImportError as exc:
    SENTRY_IMPORT_ERROR = str(exc)


def init_sentry() -> bool:
    """
    Initialize Sentry SDK if SENTRY_DSN is configured.

    Returns:
        True if Sentry was initialized, False otherwise
    """
    dsn = os.getenv("SENTRY_DSN")

    if not dsn:
        logger.info("sentry_disabled", reason="SENTRY_DSN not set")
        return False

    if not SENTRY_AVAILABLE:
        environment = str(os.getenv("ENVIRONMENT", "development")).strip().lower()
        strict_env = environment in {"production", "staging"}
        error_message = (
            "SENTRY_DSN is configured but sentry-sdk is not installed. "
            "Install sentry-sdk or unset SENTRY_DSN."
        )
        logger.error(
            "sentry_dependency_missing",
            environment=environment,
            strict_env=strict_env,
            import_error=SENTRY_IMPORT_ERROR,
        )
        if strict_env:
            raise RuntimeError(error_message)
        logger.warning("sentry_disabled", reason=error_message)
        return False

    assert sentry_sdk is not None

    environment = os.getenv("ENVIRONMENT", "development")
    release = os.getenv("APP_VERSION", "0.1.0")
    integrations: list[Any] = []
    if FastApiIntegration is not None:
        integrations.append(FastApiIntegration(transaction_style="endpoint"))
    if SqlalchemyIntegration is not None:
        integrations.append(SqlalchemyIntegration())
    if LoggingIntegration is not None:
        integrations.append(
            LoggingIntegration(
                level=None,  # Capture all as breadcrumbs
                event_level=40,  # Only ERROR+ as events
            )
        )

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"valdrix@{release}",
        # Performance monitoring
        traces_sample_rate=0.1 if environment == "production" else 1.0,
        profiles_sample_rate=0.1 if environment == "production" else 1.0,
        # Integrations
        integrations=integrations,
        # Data scrubbing
        send_default_pii=False,
        # Before send hook for filtering
        before_send=_before_send,
    )

    logger.info(
        "sentry_initialized",
        environment=environment,
        release=release,
        sample_rate=0.1 if environment == "production" else 1.0,
    )

    return True


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """
    Filter and enrich events before sending to Sentry.

    - Drops health check errors
    - Adds trace ID context
    """
    # Don't report health check failures
    if event.get("request", {}).get("url", "").endswith("/health"):
        return None

    # Add trace ID from context if available
    try:
        from app.shared.core.tracing import get_current_trace_id

        trace_id = get_current_trace_id()
        if trace_id:
            event.setdefault("tags", {})["trace_id"] = trace_id
    except ImportError:
        pass

    return event


def capture_message(message: str, level: str = "info", **extras: Any) -> None:
    """
    Capture a custom message in Sentry.
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    with sentry_sdk.new_scope() as scope:
        for key, value in extras.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(message, level)


def capture_exception(error: Exception, **extras: Any) -> None:
    """Capture an exception in Sentry with optional extra context."""
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    with sentry_sdk.new_scope() as scope:
        for key, value in extras.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_exception(error)


def set_user(
    user_id: str, tenant_id: str | None = None, email: str | None = None
) -> None:
    """
    Set user context for Sentry events.
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    sentry_sdk.set_user(
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": email,
        }
    )


def set_tenant_context(tenant_id: str, tenant_name: str | None = None) -> None:
    """
    Set tenant context for multi-tenant error tracking.
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    sentry_sdk.set_tag("tenant_id", tenant_id)
    if tenant_name:
        sentry_sdk.set_tag("tenant_name", tenant_name)
