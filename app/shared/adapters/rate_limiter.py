"""
AWS Rate Limiting Helper - Infrastructure Optimization (Phase 7: 10K Scale)

Provides rate limiting and exponential backoff for AWS API calls:
- 5 requests per second default (AWS Cost Explorer limit)
- Exponential backoff on ThrottlingException
- Automatic retry with jitter

This prevents rate limit errors at scale (10K tenants = 10K API calls).
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from functools import wraps
import structlog

logger = structlog.get_logger()

# Rate limiting constants
# CE is notoriously restrictive (5/s across account)
# EC2/CW have higher burst/refill limits but we keep them safe for 10K scale
SERVICE_LIMITS = {
    "ce": 5,          # Cost Explorer
    "cur": 10,         # Cost & Usage Report
    "ec2": 20,        # EC2
    "cw": 20,         # CloudWatch
    "trust": 10,      # Trusted Advisor
    "default": 5      # Safe fallback
}

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
MAX_RETRIES = 5
JITTER_FACTOR = 0.1  # 10% jitter

T = TypeVar('T')


class RateLimiter:
    """
    Token bucket rate limiter for AWS API calls.
    
    Ensures we don't exceed AWS service limits across all tenants.
    """
    
    def __init__(self, rate_per_second: float):
        self.rate = rate_per_second
        self.tokens = rate_per_second
        import time
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Wait until a token is available."""
        import time
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            if elapsed < 0:
                elapsed = 0
            
            # Refill tokens
            self.tokens = min(
                self.rate,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                logger.debug(
                    "rate_limit_waiting",
                    wait_seconds=round(wait_time, 3)
                )
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


# Registry of service-specific limiters
_limiters: dict[str, RateLimiter] = {}


def get_aws_rate_limiter(service: str = "ce") -> RateLimiter:
    """Get or create the rate limiter for a specific AWS service."""
    global _limiters
    service = service.lower()
    if service not in _limiters:
        rate = SERVICE_LIMITS.get(service, SERVICE_LIMITS["default"])
        _limiters[service] = RateLimiter(rate_per_second=rate)
    return _limiters[service]


async def with_rate_limit(
    coro: Callable[..., Awaitable[T]],
    *args: Any,
    service: str = "ce",
    **kwargs: Any,
) -> T:
    """
    Execute a coroutine with service-specific rate limiting.
    
    Usage:
        result = await with_rate_limit(client.get_cost_and_usage, service="ce", **params)
    """
    limiter = get_aws_rate_limiter(service)
    await limiter.acquire()
    return await coro(*args, **kwargs)


async def with_backoff(
    coro: Callable[..., Awaitable[T]],
    *args: Any,
    throttle_exceptions: tuple[type[BaseException], ...] = (),
    max_retries: int = MAX_RETRIES,
    **kwargs: Any,
) -> T:
    """
    Execute a coroutine with exponential backoff on throttling.
    
    Args:
        coro: Async function to call
        *args: Arguments for the function
        throttle_exceptions: Exception types that trigger backoff
        max_retries: Maximum retry attempts
        **kwargs: Keyword arguments for the function
    
    Returns:
        Result of the coroutine
    
    Raises:
        The last exception if all retries fail
    """
    from botocore.exceptions import ClientError
    
    backoff = INITIAL_BACKOFF_SECONDS
    last_exception: BaseException | None = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coro(*args, **kwargs)
        
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            
            # Check if it's a throttling error
            if error_code in ("ThrottlingException", "Throttling", "TooManyRequestsException"):
                last_exception = e
                
                if attempt >= max_retries:
                    logger.warning(
                        "aws_throttle_max_retries",
                        attempt=attempt,
                        error=str(e)
                    )
                    raise
                
                # Add jitter to prevent thundering herd
                jitter = random.uniform(-JITTER_FACTOR, JITTER_FACTOR) * backoff
                sleep_time = backoff + jitter
                
                logger.info(
                    "aws_throttle_backoff",
                    attempt=attempt,
                    sleep_seconds=round(sleep_time, 2),
                    error_code=error_code
                )
                
                await asyncio.sleep(sleep_time)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            else:
                # Non-throttling error, don't retry
                raise
        
        except throttle_exceptions as e:
            last_exception = e
            
            if attempt >= max_retries:
                raise
            
            jitter = random.uniform(-JITTER_FACTOR, JITTER_FACTOR) * backoff
            sleep_time = backoff + jitter
            
            logger.info(
                "aws_backoff",
                attempt=attempt,
                sleep_seconds=round(sleep_time, 2),
                error=str(e)
            )
            
            await asyncio.sleep(sleep_time)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
    
    if last_exception:
        raise last_exception
    
    raise RuntimeError("Unexpected state in with_backoff")


def rate_limited(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """
    Decorator to apply rate limiting to an async function.
    
    Usage:
        @rate_limited
        async def get_costs():
            ...
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        limiter = get_aws_rate_limiter()
        await limiter.acquire()
        return await func(*args, **kwargs)
    return wrapper
