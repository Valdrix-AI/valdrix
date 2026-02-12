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

# Optional import - Sentry is only used in production
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    logger.info("sentry_sdk_not_installed", message="Install sentry-sdk for error tracking")


def init_sentry() -> bool:
    """
    Initialize Sentry SDK if SENTRY_DSN is configured.
    
    Returns:
        True if Sentry was initialized, False otherwise
    """
    if not SENTRY_AVAILABLE:
        logger.info("sentry_disabled", reason="sentry-sdk not installed")
        return False
    
    dsn = os.getenv("SENTRY_DSN")
    
    if not dsn:
        logger.info("sentry_disabled", reason="SENTRY_DSN not set")
        return False
    
    environment = os.getenv("ENVIRONMENT", "development")
    release = os.getenv("APP_VERSION", "0.1.0")
    
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"valdrix@{release}",
        
        # Performance monitoring
        traces_sample_rate=0.1 if environment == "production" else 1.0,
        profiles_sample_rate=0.1 if environment == "production" else 1.0,
        
        # Integrations
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=None,  # Capture all as breadcrumbs
                event_level=40,  # Only ERROR+ as events
            ),
        ],
        
        # Data scrubbing
        send_default_pii=False,
        
        # Before send hook for filtering
        before_send=_before_send,
    )
    
    logger.info(
        "sentry_initialized",
        environment=environment,
        release=release,
        sample_rate=0.1 if environment == "production" else 1.0
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
    if not SENTRY_AVAILABLE:
        return

    with sentry_sdk.push_scope() as scope:
        for key, value in extras.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(message, level)


def capture_exception(error: Exception, **extras: Any) -> None:
    """Capture an exception in Sentry with optional extra context."""
    if not SENTRY_AVAILABLE:
        return

    with sentry_sdk.push_scope() as scope:
        for key, value in extras.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_exception(error)


def set_user(
    user_id: str, tenant_id: str | None = None, email: str | None = None
) -> None:
    """
    Set user context for Sentry events.
    """
    if not SENTRY_AVAILABLE:
        return

    sentry_sdk.set_user({
        "id": user_id,
        "tenant_id": tenant_id,
        "email": email,
    })


def set_tenant_context(tenant_id: str, tenant_name: str | None = None) -> None:
    """
    Set tenant context for multi-tenant error tracking.
    """
    if not SENTRY_AVAILABLE:
        return

    sentry_sdk.set_tag("tenant_id", tenant_id)
    if tenant_name:
        sentry_sdk.set_tag("tenant_name", tenant_name)
