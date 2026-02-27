"""
Rate Limiting Middleware for Valdrix

Provides API rate limiting using slowapi (built on limits library).
Configurable via environment variables.
"""

from typing import Any, Callable, Optional, cast
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
import hashlib
import structlog
from redis.asyncio import Redis, from_url

from app.shared.core.config import get_settings

__all__ = [
    "get_limiter",
    "setup_rate_limiting",
    "rate_limit",
    "global_rate_limit",
    "global_limit_key",
    "standard_limit",
    "auth_limit",
    "analysis_limit",
    "RateLimitExceeded",
    "_rate_limit_exceeded_handler",
]

logger = structlog.get_logger()

_limiter: Limiter | None = None
_redis_client: Redis | None = None


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
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            return f"token:{token_hash}"
        except Exception:
            pass

    return get_remote_address(request)


def get_limiter() -> Limiter:
    """Lazy initialization of the Limiter instance.

    ADR (Finding #6): Production deployments MUST set REDIS_URL for distributed
    rate limiting. The ``memory://`` fallback is intentionally kept for
    single-instance dev/test, but it is NOT suitable for multi-replica
    deployments where limits must be shared across processes.
    """
    global _limiter
    if _limiter is None:
        settings = get_settings()
        storage_uri = settings.REDIS_URL or "memory://"
        is_production_like = settings.ENVIRONMENT.lower() in ("production", "staging")
        if (
            is_production_like
            and not settings.REDIS_URL
            and not settings.ALLOW_IN_MEMORY_RATE_LIMITS
        ):
            raise RuntimeError(
                "Distributed rate limiting is required in staging/production. "
                "Set REDIS_URL (or explicitly ALLOW_IN_MEMORY_RATE_LIMITS=true for break-glass)."
            )
        if is_production_like and not settings.REDIS_URL:
            logger.warning(
                "rate_limiting_in_memory_break_glass",
                msg="REDIS_URL is not set. In-memory rate limiting is enabled via "
                "ALLOW_IN_MEMORY_RATE_LIMITS and should be temporary.",
            )
            
        _limiter = Limiter(
            key_func=context_aware_key,
            storage_uri=storage_uri,
            strategy="fixed-window",
            enabled=getattr(settings, "RATELIMIT_ENABLED", True)
            and not getattr(settings, "TESTING", False),
        )
    return _limiter


def get_redis_client() -> Redis | None:
    """Lazy initialization of the Redis client for rate limiting and health checks."""
    global _redis_client
    settings = get_settings()
    # Tests should use in-memory fallback by default to avoid external network coupling
    # and unclosed transport warnings from ephemeral event loops.
    if getattr(settings, "TESTING", False) is True and not getattr(
        settings, "ALLOW_REDIS_IN_TESTS", False
    ):
        return None
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
        redis_from_url = cast(Callable[..., Redis], from_url)
        _redis_client = redis_from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def setup_rate_limiting(app: FastAPI) -> None:
    """
    Configure rate limiting for the FastAPI application.
    """
    limiter = get_limiter()
    # Add rate limit exceeded handler
    app.state.limiter = limiter

    def _rate_limit_handler(request: Request, exc: Exception) -> Any:
        return _rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))

    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    logger.info("rate_limiting_configured")


# Rate limit decorators for use in routes
def rate_limit(
    limit: str | Callable[[Request], str] = "100/minute",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to apply rate limiting to an endpoint."""
    # Finding #L3: If we bypass the decorator here based on settings.TESTING,
    # it captures the state at import time. Instead, we always return the 
    # limiter's decorator, which internally checks its 'enabled' status 
    # during each request.
    return cast(
        Callable[[Callable[..., Any]], Callable[..., Any]], get_limiter().limit(limit)
    )


def global_limit_key(namespace: str) -> Callable[[Request], str]:
    """
    Build a stable cross-tenant limiter key for shared fairness controls.
    """

    safe_namespace = "".join(
        ch if (ch.isalnum() or ch in {"_", "-", ".", ":"}) else "_"
        for ch in str(namespace or "").strip().lower()
    )
    if not safe_namespace:
        safe_namespace = "global"
    key = f"global:{safe_namespace}"

    def _key(request: Request | None = None) -> str:
        del request
        return key

    return _key


def global_rate_limit(
    limit: str | Callable[[Request], str] = "1000/minute",
    *,
    namespace: str = "default",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Apply a route-level global throttle shared across tenants.
    """

    return cast(
        Callable[[Callable[..., Any]], Callable[..., Any]],
        get_limiter().limit(limit, key_func=global_limit_key(namespace)),
    )


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
        raw_tier = getattr(request.state, "tier", "starter")
        if hasattr(raw_tier, "value"):
            tier = str(getattr(raw_tier, "value")).strip().lower()
        elif isinstance(raw_tier, str):
            tier = raw_tier.strip().lower()
        else:
            tier = "starter"
        if not tier:
            tier = "starter"
    except (AttributeError, Exception):
        tier = "starter"

    # Mapping of tier to rate limit (per hour to prevent burst costs)
    limits = {
        "free": "1/hour",
        "starter": "2/hour",
        "growth": "10/hour",
        "pro": "50/hour",
        "enterprise": "200/hour",
    }

    return limits.get(tier, "1/hour")


def standard_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the standard API limit decorator."""
    return rate_limit(STANDARD_LIMIT)(func)


def auth_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the authenticated-route API limit decorator."""
    return rate_limit(AUTH_LIMIT)(func)


# Dynamic analysis limit decorator
def analysis_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that applies a dynamic analysis limit based on tenant tier."""
    if get_settings().TESTING:
        return func
    # Pass the callable (not its result) so it's evaluated per-request
    decorated = get_limiter().limit(get_analysis_limit)(func)
    return cast(Callable[..., Any], decorated)


# Remediation-specific rate limiting (BE-SEC-3)
REMEDIATION_LIMIT_PER_HOUR = 50  # Max remediations per tenant per hour

_remediation_counts: dict[
    str, dict[str, float | int]
] = {}  # In-memory fallback when Redis unavailable
_remediation_last_cleanup_at: float = 0.0
_REMEDIATION_WINDOW_SECONDS = 3600
_REMEDIATION_STALE_RETENTION_SECONDS = _REMEDIATION_WINDOW_SECONDS * 2
_REMEDIATION_CLEANUP_INTERVAL_SECONDS = 300


def _cleanup_stale_remediation_counts(current_time: float) -> None:
    """
    Prevent unbounded growth for local in-memory fallback rate-limit state.
    """
    global _remediation_last_cleanup_at
    if (
        current_time - _remediation_last_cleanup_at
        < _REMEDIATION_CLEANUP_INTERVAL_SECONDS
    ):
        return

    stale_before = current_time - _REMEDIATION_STALE_RETENTION_SECONDS
    stale_keys = [
        key
        for key, value in _remediation_counts.items()
        if float(value.get("window_start", 0.0)) < stale_before
    ]
    for key in stale_keys:
        _remediation_counts.pop(key, None)
    _remediation_last_cleanup_at = current_time


async def check_remediation_rate_limit(
    tenant_id: Any, action: str, limit: int = REMEDIATION_LIMIT_PER_HOUR
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

    # Finding #6: Enforce Redis for production/staging to ensure distributed correctness
    settings = get_settings()
    is_prod = settings.ENVIRONMENT.lower() in ("production", "staging")
    
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
                    limit=limit,
                )
                return False
            return True
        except Exception as e:
            logger.error("remediation_rate_limit_redis_error", error=str(e))
            # Fall through to memory fallback if NOT in production
            if is_prod:
                return False

    # Finding #6: Enforce Redis for production/staging
    if is_prod:
        logger.error("redis_unavailable_in_production", tenant_id=tenant_key, action=action)
        return False

    # Memory fallback for local/single-instance deployments
    current_time = time.time()
    window_key = f"{tenant_key}:{action}"
    _cleanup_stale_remediation_counts(current_time)

    if window_key not in _remediation_counts:
        _remediation_counts[window_key] = {"count": 0, "window_start": current_time}

    entry = _remediation_counts[window_key]

    # Reset window if expired (1 hour)
    if current_time - entry["window_start"] > _REMEDIATION_WINDOW_SECONDS:
        entry["count"] = 0
        entry["window_start"] = current_time

    if entry["count"] >= limit:
        logger.warning(
            "remediation_rate_limited",
            tenant_id=tenant_key,
            action=action,
            current=entry["count"],
            limit=limit,
        )
        return False

    entry["count"] += 1
    return True
