"""
Rate Limiting Middleware for Valdrix

Provides API rate limiting using slowapi (built on limits library).
Configurable via environment variables.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

def context_aware_key(request: Request) -> str:
    """
    Identifies the requester for rate limiting.
    1. Uses tenant_id if user is authenticated (B2B fairness).
    2. Falls back to sub from JWT if auth hasn't run but token exists (Prevents NAT issues).
    3. Falls back to remote IP (Defense-in-depth).
    """
    # Try request state (already populated by get_current_user dependency)
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return f"tenant:{tenant_id}"
    
    # Fast check for Authorization header (no DB lookup)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            # We use the sub directly for identification (NAT-safe)
            # No need for full verification here as it's just for identification,
            # downstream dependencies will handle real verification.
            import jwt
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    return get_remote_address(request)

# Create limiter instance with context-aware identification and distributed storage
settings = get_settings()
storage_uri = settings.REDIS_URL or "memory://"

limiter = Limiter(
    key_func=context_aware_key,
    storage_uri=storage_uri,
    strategy="fixed-window" # Standard strategy
)


def setup_rate_limiting(app: FastAPI) -> None:
    """
    Configure rate limiting for the FastAPI application.

    Default limits (configurable via settings):
    - 100 requests/minute for general API
    - 10 requests/minute for analysis endpoints (LLM calls)
    - 30 requests/minute for authentication
    """
    get_settings()

    # Add rate limit exceeded handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    logger.info("rate_limiting_configured", default_limit="100/minute")


# Rate limit decorators for use in routes
def rate_limit(limit: str = "100/minute"):
    """
    Decorator to apply rate limiting to an endpoint.

    Usage:
        @router.get("/expensive-operation")
        @rate_limit("10/minute")
        async def expensive_operation():
            ...

    Args:
        limit: Rate limit string (e.g., "100/minute", "10/second", "1000/hour")
    """
    return limiter.limit(limit)


# Pre-configured rate limiters for common use cases
standard_limit = limiter.limit("100/minute")
analysis_limit = limiter.limit("10/minute")  # For LLM-based analysis (expensive)
auth_limit = limiter.limit("30/minute")      # For auth endpoints
