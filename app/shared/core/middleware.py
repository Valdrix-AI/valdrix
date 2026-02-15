from collections.abc import Awaitable, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request
import uuid
import structlog
from app.shared.core.config import get_settings
from app.shared.core.tracing import set_correlation_id


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()

        response = await call_next(request)

        # HSTS: Disable in debug mode for local development
        # HSTS: Disable in debug mode for local development, only send on HTTPS
        if request.url.scheme == "https":
            if settings.DEBUG:
                response.headers["Strict-Transport-Security"] = "max-age=0"
            else:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains; preload"
                )

        if "X-Content-Type-Options" not in response.headers:
            response.headers["X-Content-Type-Options"] = "nosniff"

        if "X-Frame-Options" not in response.headers:
            response.headers["X-Frame-Options"] = "DENY"

        # Skip strict CSP for Swagger UI (requires inline scripts)
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            return response

        # CSP connect-src: Restrict based on allowed origins from config
        # Convert CORS_ORIGINS list to a space-separated string for CSP
        allowed_origins = " ".join(settings.CORS_ORIGINS)
        connect_src = f"'self' {allowed_origins}"

        csp_policy = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "  # Allow inline styles for Svelte/shadcn
            f"connect-src {connect_src}; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self';"
        )
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = csp_policy

        if "Referrer-Policy" not in response.headers:
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if "Permissions-Policy" not in response.headers:
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=(), interest-cohort=()"
            )

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique X-Request-ID into the logs and response.
    Integrates with app.shared.core.tracing for cross-process correlation.
    NOTE: This middleware trusts the X-Request-ID header if provided by the client.
    This is intended for correlation and debugging, not as a security principal.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Set unified tracing context
        set_correlation_id(request_id)

        # Store in state for easy access in endpoints and tests
        request.state.request_id = request_id

        # Log injection via contextvars (supported by structlog)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
