"""
Unified Error Governance (2026 Standards)

Centrally handles exception classification, structured logging,
and OpenTelemetry span recording to ensure 100% observability.
"""

from typing import Optional
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace

from app.shared.core.exceptions import ValdrixException
from app.shared.core.ops_metrics import API_ERRORS_TOTAL

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


def handle_exception(
    request: Request, exc: Exception, error_id: Optional[str] = None
) -> JSONResponse:
    """
    Classifies and records exceptions, returning a standardized JSON response.
    """
    from uuid import uuid4

    error_id = error_id or str(uuid4())

    # 1. Classification & Sanitization
    from app.shared.core.config import get_settings
    settings = get_settings()
    is_prod = settings.ENVIRONMENT.lower() in ("production", "staging")

    if isinstance(exc, ValdrixException):
        valdrix_exc = exc
        # SEC-07: Sanitize message in production if it's not a known safe-to-leak type
        if is_prod:
            # Only allow specific safe codes or manually verified safe messages
            safe_codes = {"auth_error", "not_found", "budget_exceeded", "kill_switch_triggered"}
            if valdrix_exc.code not in safe_codes:
                valdrix_exc.message = "An error occurred while processing your request"
    elif isinstance(exc, ValueError):
        # Business logic validation errors should be 400
        msg = "Invalid request parameters" if is_prod else str(exc)
        valdrix_exc = ValdrixException(
            message=msg,
            code="value_error",
            status_code=400,
        )
        # Log the real cause
        logger.warning(
            "business_validation_error",
            error=str(exc),
            error_id=error_id,
            path=request.url.path,
        )
    else:
        # Generic internal error for everything else
        msg = "An unexpected internal error occurred" if is_prod else str(exc)
        valdrix_exc = ValdrixException(
            message=msg,
            code="internal_error",
            status_code=500,
        )
        # Log the original cause for internal debugging
        logger.exception(
            "unhandled_raw_exception",
            error=str(exc),
            error_id=error_id,
            path=request.url.path,
        )

    # 2. OTel Recording
    with tracer.start_as_current_span("handle_exception") as span:
        span.set_attribute("error.id", error_id)
        span.set_attribute("http.path", request.url.path)
        span.set_attribute("http.method", request.method)

        # Call the built-in OTel recorder on the exception
        if hasattr(valdrix_exc, "record_to_otel"):
            valdrix_exc.record_to_otel()
        else:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))

    # 3. Metrics
    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=valdrix_exc.status_code,
    ).inc()

    # 4. Structured Logging
    logger.error(
        "api_error",
        error_id=error_id,
        code=valdrix_exc.code,
        message=valdrix_exc.message,
        status_code=valdrix_exc.status_code,
        path=request.url.path,
        details=valdrix_exc.details,
    )

    # 5. Production Response (Sanitized)
    return JSONResponse(
        status_code=valdrix_exc.status_code,
        content={
            "error": {
                "message": valdrix_exc.message,
                "code": valdrix_exc.code,
                "id": error_id,
                # Details are only included if they are safe (already sanitized in Exception classes)
                "details": valdrix_exc.details if valdrix_exc.details else None,
            }
        },
    )
