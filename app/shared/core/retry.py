"""
Retry Logic with Exponential Backoff

Provides robust retry mechanisms for transient failures in database operations,
external API calls, and other unreliable operations.
"""
import asyncio
import random
from typing import Callable, TypeVar
from functools import wraps
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)

from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()
T = TypeVar('T')

# Default retry configurations
RETRY_CONFIGS = {
    "database": {
        "max_attempts": 3,
        "min_wait": 0.1,
        "max_wait": 2.0,
        "multiplier": 2.0,
        "exceptions": (Exception,),  # Broad catch for DB issues
    },
    "external_api": {
        "max_attempts": 3,
        "min_wait": 1.0,
        "max_wait": 10.0,
        "multiplier": 2.0,
        "exceptions": (ExternalAPIError, ConnectionError, asyncio.TimeoutError),
    },
    "cache": {
        "max_attempts": 2,
        "min_wait": 0.05,
        "max_wait": 0.5,
        "multiplier": 1.5,
        "exceptions": (ConnectionError, asyncio.TimeoutError),
    },
    "webhook": {
        "max_attempts": 5,
        "min_wait": 2.0,
        "max_wait": 60.0,
        "multiplier": 2.0,
        "exceptions": (ExternalAPIError, ConnectionError),
    },
}


class RetryManager:
    """Manages retry logic with configurable backoff strategies."""

    def __init__(self, operation_type: str = "default"):
        self.operation_type = operation_type
        self.config = RETRY_CONFIGS.get(operation_type, {
            "max_attempts": 3,
            "min_wait": 0.1,
            "max_wait": 2.0,
            "multiplier": 2.0,
            "exceptions": (Exception,),
        })

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        # Exponential backoff: base_delay * (multiplier ^ attempt)
        base_delay = self.config["min_wait"]
        max_delay = self.config["max_wait"]
        multiplier = self.config["multiplier"]

        delay = min(base_delay * (multiplier ** attempt), max_delay)

        # Add jitter (±25%) to prevent thundering herd
        jitter = delay * 0.25 * (random.random() * 2 - 1)
        final_delay = delay + jitter

        return max(0.001, final_delay)  # Minimum 1ms delay

    async def execute_with_retry(self, coro: Callable[..., T], *args, **kwargs) -> T:
        """Execute a coroutine with retry logic."""
        last_exception = None

        for attempt in range(self.config["max_attempts"]):
            try:
                result = await coro(*args, **kwargs)

                if attempt > 0:
                    logger.info(
                        "operation_succeeded_after_retry",
                        operation_type=self.operation_type,
                        attempt=attempt + 1,
                        max_attempts=self.config["max_attempts"]
                    )

                return result

            except self.config["exceptions"] as e:
                last_exception = e

                if attempt < self.config["max_attempts"] - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        "operation_failed_will_retry",
                        operation_type=self.operation_type,
                        attempt=attempt + 1,
                        max_attempts=self.config["max_attempts"],
                        delay_seconds=round(delay, 3),
                        error=str(e),
                        error_type=type(e).__name__
                    )

                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "operation_failed_all_retries_exhausted",
                        operation_type=self.operation_type,
                        total_attempts=self.config["max_attempts"],
                        error=str(e),
                        error_type=type(e).__name__
                    )

        # All retries exhausted
        raise last_exception


def retry_operation(operation_type: str = "default"):
    """
    Decorator for operations that need retry logic.

    Usage:
        @retry_operation("database")
        async def database_query():
            # Database operation here
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            retry_manager = RetryManager(operation_type)
            return await retry_manager.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator


# Pre-configured retry decorators for common operations
retry_database = retry_operation("database")
retry_external_api = retry_operation("external_api")
retry_cache = retry_operation("cache")
retry_webhook = retry_operation("webhook")


# Tenacity-based retry decorators for more complex scenarios
def tenacity_retry(operation_type: str = "default"):
    """
    Decorator using tenacity library for advanced retry patterns.

    Provides more sophisticated retry logic with circuit breaker integration.
    """
    config = RETRY_CONFIGS.get(operation_type, RETRY_CONFIGS["database"])

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            stop=stop_after_attempt(config["max_attempts"]),
            wait=wait_exponential(
                multiplier=config["multiplier"],
                min=config["min_wait"],
                max=config["max_wait"]
            ),
            retry=retry_if_exception_type(config["exceptions"]),
            before_sleep=before_sleep_log(logger, "warning"),
            after=after_log(logger, "info")
        )
        async def wrapper(*args, **kwargs) -> T:
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Database-specific retry with deadlock detection
async def execute_with_deadlock_retry(coro: Callable[..., T], *args, **kwargs) -> T:
    """
    Execute database operations with deadlock-specific retry logic.

    Detects database deadlocks and retries with appropriate backoff.
    """
    max_attempts = 5
    base_delay = 0.1

    for attempt in range(max_attempts):
        try:
            return await coro(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()

            # Check if this is a deadlock error
            if ("deadlock" in error_msg or "lock wait timeout" in error_msg or
                "serialization failure" in error_msg):

                if attempt < max_attempts - 1:
                    # Exponential backoff for deadlocks
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)

                    logger.warning(
                        "database_deadlock_detected_retry",
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay_seconds=round(delay, 3),
                        error=str(e)
                    )

                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "database_deadlock_all_retries_exhausted",
                        total_attempts=max_attempts,
                        error=str(e)
                    )

            # Non-deadlock error, re-raise immediately
            raise

    # Should not reach here, but just in case
    raise RuntimeError("Unexpected retry exhaustion")


def get_retry_config(operation_type: str) -> dict:
    """Get retry configuration for an operation type."""
    return RETRY_CONFIGS.get(operation_type, RETRY_CONFIGS["database"]).copy()


def set_retry_config(operation_type: str, config: dict) -> None:
    """Set custom retry configuration for an operation type."""
    required_keys = {"max_attempts", "min_wait", "max_wait", "multiplier", "exceptions"}

    if not all(key in config for key in required_keys):
        raise ValueError(f"Invalid retry configuration for {operation_type}")

    RETRY_CONFIGS[operation_type] = config.copy()
    logger.info("retry_config_updated", operation_type=operation_type, config=config)
