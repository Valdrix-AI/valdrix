from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import uuid
import structlog

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from app.shared.core.config import get_settings
        settings = get_settings()

        response = await call_next(request)

        # HSTS: Disable in debug mode for local development
        if settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=0"
        else:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        response.headers["X-Content-Type-Options"] = "nosniff"
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
        response.headers["Content-Security-Policy"] = csp_policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique X-Request-ID into the logs and response.
    Integrates with app.shared.core.tracing for cross-process correlation.
    NOTE: This middleware trusts the X-Request-ID header if provided by the client.
    This is intended for correlation and debugging, not as a security principal.
    """
    async def dispatch(self, request: Request, call_next):
        from app.shared.core.tracing import set_correlation_id
        
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Set unified tracing context
        set_correlation_id(request_id)

        # Log injection via contextvars (supported by structlog)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
