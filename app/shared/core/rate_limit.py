"""
Rate Limiting Middleware for Valdrix

Provides API rate limiting using slowapi (built on limits library).
Configurable via environment variables.
"""

from typing import Optional, Any, Callable, Awaitable
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
import structlog
from redis.asyncio import Redis, from_url

from app.shared.core.config import get_settings

__all__ = [
    "get_limiter", 
    "setup_rate_limiting", 
    "rate_limit", 
    "standard_limit", 
    "auth_limit", 
    "analysis_limit", 
    "RateLimitExceeded", 
    "_rate_limit_exceeded_handler"
]

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
            # SEC-02: Hash token for rate limiting instead of decoding
            # This prevents bypass via forged JWTs with same 'sub' claim
            import hashlib
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            return f"token:{token_hash}"
        except Exception:
            pass

    return get_remote_address(request)

def get_limiter() -> Limiter:
    """Lazy initialization of the Limiter instance."""
    global _limiter
    if _limiter is None:
        settings = get_settings()
        storage_uri = settings.REDIS_URL or "memory://"
        _limiter = Limiter(
            key_func=context_aware_key,
            storage_uri=storage_uri,
            strategy="fixed-window",
            enabled=getattr(settings, "RATELIMIT_ENABLED", True)
        )
    return _limiter

_limiter = None
_redis_client: Optional[Redis] = None

def get_redis_client() -> Optional[Redis]:
    """Lazy initialization of the Redis client for rate limiting and health checks."""
    global _redis_client
    settings = get_settings()
    if not settings.REDIS_URL:
        return None
    
    # Check if client exists and ensure it is tied to the current running loop
    if _redis_client is not None:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            # If the client's loop is not the current one, reset it
            if getattr(_redis_client, "_loop", None) != loop:
                _redis_client = None
        except (RuntimeError, AttributeError):
            _redis_client = None

    if _redis_client is None:
        _redis_client = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client

def setup_rate_limiting(app: FastAPI) -> None:
    """
    Configure rate limiting for the FastAPI application.
    """
    limiter = get_limiter()
    # Add rate limit exceeded handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("rate_limiting_configured")

# Rate limit decorators for use in routes
def rate_limit(limit: str = "100/minute"):
    """Decorator to apply rate limiting to an endpoint."""
    if get_settings().TESTING:
        return lambda x: x
    return get_limiter().limit(limit)

# Pre-configured rate limits (now using strings for delay)
# Route handlers can use @rate_limit("100/minute") or these helpers
STANDARD_LIMIT = "100/minute"
AUTH_LIMIT = "30/minute"

def get_analysis_limit(request: Optional[Request] = None) -> str:
    """
    BE-LLM-4: Dynamic rate limiting based on tenant tier.
    Protects LLM operational costs while rewarding higher tiers.
    """
    if not request:
        return "1/hour"
        
    try:
        tier = getattr(request.state, "tier", "starter")
        # Ensure we don't return a Mock object as the tier string
        if not isinstance(tier, str):
            tier = "starter"
    except (AttributeError, Exception):
        tier = "starter"
            
    # Mapping of tier to rate limit (per hour to prevent burst costs)
    limits = {
        "trial": "1/hour",
        "starter": "2/hour",
        "growth": "10/hour",
        "pro": "50/hour",
        "enterprise": "200/hour"
    }
    
    return limits.get(tier, "1/hour")

# Backward-compatible decorators for imports expecting callable
# Usage: @auth_limit (as decorator, no parentheses)
def _make_limit_decorator(limit_str: str):
    """Creates a decorator that applies the given rate limit."""
    def decorator(func):
        # Apply the rate limit at decoration time
        return rate_limit(limit_str)(func)
    return decorator

# Non-parenthesized decorators (default limits)
standard_limit = _make_limit_decorator(STANDARD_LIMIT)
auth_limit = _make_limit_decorator(AUTH_LIMIT)

# Dynamic analysis limit decorator
def analysis_limit(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator that applies a dynamic analysis limit based on tenant tier."""
    if get_settings().TESTING:
        return func
    return get_limiter().limit(get_analysis_limit)(func)



# Remediation-specific rate limiting (BE-SEC-3)
REMEDIATION_LIMIT_PER_HOUR = 50  # Max remediations per tenant per hour

_remediation_counts: dict = {}  # In-memory fallback when Redis unavailable

async def check_remediation_rate_limit(
    tenant_id,
    action: str,
    limit: int = REMEDIATION_LIMIT_PER_HOUR
) -> bool:
    """
    Check if a remediation action is allowed under rate limits.
    
    Returns True if allowed, False if rate limited.
    Uses Redis if available, memory fallback otherwise.
    """
    import time
    from uuid import UUID
    
    tenant_key = str(tenant_id) if isinstance(tenant_id, UUID) else tenant_id
    redis = get_redis_client()
    
    if redis:
        try:
            # Use Redis for distributed rate limiting
            key = f"remediation_rate:{tenant_key}:{action}"
            current = await redis.incr(key)
            if current == 1:
                # Set expiry on first increment (1 hour window)
                await redis.expire(key, 3600)
            
            if current > limit:
                logger.warning(
                    "remediation_rate_limited",
                    tenant_id=tenant_key,
                    action=action,
                    current=current,
                    limit=limit
                )
                return False
            return True
        except Exception as e:
            logger.error("remediation_rate_limit_redis_error", error=str(e))
            # Fall through to memory fallback
    
    # Memory fallback for single-instance deployments
    current_time = time.time()
    window_key = f"{tenant_key}:{action}"
    
    if window_key not in _remediation_counts:
        _remediation_counts[window_key] = {"count": 0, "window_start": current_time}
    
    entry = _remediation_counts[window_key]
    
    # Reset window if expired (1 hour)
    if current_time - entry["window_start"] > 3600:
        entry["count"] = 0
        entry["window_start"] = current_time
    
    if entry["count"] >= limit:
        logger.warning(
            "remediation_rate_limited",
            tenant_id=tenant_key,
            action=action,
            current=entry["count"],
            limit=limit
        )
        return False
    
    entry["count"] += 1
    return True
