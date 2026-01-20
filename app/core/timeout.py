"""
Request Timeout Middleware for Valdrix

Enforces maximum request duration to prevent zombie scans from blocking workers.
"""

import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import structlog


from app.core.config import get_settings
logger = structlog.get_logger()

# Default timeout in seconds (configurable via settings)
DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request timeouts.

    Cancels requests that exceed the configured timeout to prevent
    resource exhaustion from long-running operations.
    """

    def __init__(self, app, timeout_seconds: int | None = None):
        super().__init__(app)
        settings = get_settings()
        self.timeout_seconds = timeout_seconds or getattr(settings, "REQUEST_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(
                "request_timeout",
                path=request.url.path,
                method=request.method,
                timeout_seconds=self.timeout_seconds
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"Request timed out after {self.timeout_seconds} seconds",
                    "error": "gateway_timeout"
                }
            )
