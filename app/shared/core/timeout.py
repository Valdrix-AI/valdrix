"""
Request Timeout Middleware for Valdrix

Enforces maximum request duration to prevent zombie scans from blocking workers.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from functools import wraps
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.shared.core.config import get_settings
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()

# Default timeout in seconds (configurable via settings)
DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


T = TypeVar("T")

# Default timeout configurations (seconds)
TIMEOUT_CONFIGS: dict[str, dict[str, float]] = {
    "default": {
        "total": 30.0,
        "connect": 10.0,
        "read": 20.0,
    },
    "llm_api": {
        "total": 30.0,  # Total request timeout
        "connect": 10.0,  # Connection establishment timeout
        "read": 20.0,  # Response read timeout
    },
    "cloud_api": {
        "total": 60.0,  # Cloud provider APIs (AWS, GCP, Azure)
        "connect": 15.0,
        "read": 45.0,
    },
    "webhook": {
        "total": 10.0,  # Webhook delivery
        "connect": 5.0,
        "read": 5.0,
    },
    "cache": {
        "total": 2.0,  # Cache operations
        "connect": 1.0,
        "read": 1.0,
    },
    "database": {
        "total": 10.0,  # Database operations
        "connect": 2.0,
        "read": 8.0,
    },
}


class TimeoutManager:
    """Manages timeouts for external operations."""

    def __init__(self, operation_type: str = "default"):
        self.operation_type = operation_type
        self.config = TIMEOUT_CONFIGS.get(
            operation_type,
            {
                "total": 30.0,
                "connect": 10.0,
                "read": 20.0,
            },
        )

    async def execute_with_timeout(
        self,
        coro: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a coroutine with timeout handling."""
        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                coro(*args, **kwargs), timeout=self.config["total"]
            )

            execution_time = time.perf_counter() - start_time
            logger.debug(
                "operation_completed_within_timeout",
                operation_type=self.operation_type,
                execution_time_seconds=round(execution_time, 3),
                timeout_seconds=self.config["total"],
            )

            return result

        except asyncio.TimeoutError:
            execution_time = time.perf_counter() - start_time
            logger.warning(
                "operation_timed_out",
                operation_type=self.operation_type,
                execution_time_seconds=round(execution_time, 3),
                timeout_seconds=self.config["total"],
            )

            raise ExternalAPIError(
                f"Operation timed out after {self.config['total']} seconds",
                code="timeout_error",
                details={
                    "operation_type": self.operation_type,
                    "timeout_seconds": self.config["total"],
                    "execution_time_seconds": round(execution_time, 3),
                },
            )

        except Exception as e:
            execution_time = time.perf_counter() - start_time
            logger.error(
                "operation_failed",
                operation_type=self.operation_type,
                execution_time_seconds=round(execution_time, 3),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise


def timeout_operation(
    operation_type: str = "default",
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for operations that need timeout handling.

    Usage:
        @timeout_operation("llm_api")
        async def call_openai_api():
            # API call here
            pass
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            timeout_manager = TimeoutManager(operation_type)
            return await timeout_manager.execute_with_timeout(func, *args, **kwargs)

        return wrapper

    return decorator


@asynccontextmanager
async def timeout_context(
    operation_type: str = "default",
    custom_timeout: float | None = None,
) -> AsyncIterator[TimeoutManager]:
    """
    Context manager for timeout handling.

    Usage:
        async with timeout_context("llm_api", custom_timeout=60.0):
            await some_long_running_operation()
    """
    timeout_manager = TimeoutManager(operation_type)

    if custom_timeout:
        timeout_manager.config["total"] = custom_timeout

    yield timeout_manager


def get_timeout_config(operation_type: str) -> dict[str, float]:
    """Get timeout configuration for an operation type."""
    return TIMEOUT_CONFIGS.get(operation_type, TIMEOUT_CONFIGS["default"]).copy()


def validate_timeout_config(
    operation_type: str, config: dict[str, int | float]
) -> bool:
    """Validate timeout configuration."""
    required_keys = {"total", "connect", "read"}

    if not all(key in config for key in required_keys):
        return False

    # Ensure all values are positive numbers
    return all(isinstance(v, (int, float)) and v > 0 for v in config.values())


def set_timeout_config(operation_type: str, config: dict[str, int | float]) -> None:
    """Set custom timeout configuration for an operation type."""
    if not validate_timeout_config(operation_type, config):
        raise ValueError(f"Invalid timeout configuration for {operation_type}")

    TIMEOUT_CONFIGS[operation_type] = config.copy()
    logger.info("timeout_config_updated", operation_type=operation_type, config=config)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request timeouts.

    Cancels requests that exceed the configured timeout to prevent
    resource exhaustion from long-running operations.
    """

    def __init__(self, app: ASGIApp, timeout_seconds: int | None = None) -> None:
        super().__init__(app)
        settings = get_settings()
        self.timeout_seconds = timeout_seconds or getattr(
            settings, "REQUEST_TIMEOUT", DEFAULT_TIMEOUT_SECONDS
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await asyncio.wait_for(
                call_next(request), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(
                "request_timeout",
                path=request.url.path,
                method=request.method,
                timeout_seconds=self.timeout_seconds,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"Request timed out after {self.timeout_seconds} seconds",
                    "error": "gateway_timeout",
                },
            )
