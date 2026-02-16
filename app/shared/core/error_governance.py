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

    # 1. Classification
    if isinstance(exc, ValdrixException):
        valdrix_exc = exc
    else:
        # Wrap unknown exceptions as ExternalAPIError or Generic Internal
        # in a production environment, we should be strictly specific.
        valdrix_exc = ValdrixException(
            message="An unexpected internal error occurred",
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
