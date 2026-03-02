"""
Circuit Breaker Pattern Implementation

Provides fault tolerance for external service calls with automatic recovery.
Implements the Circuit Breaker pattern to prevent cascade failures.
"""

import asyncio
import time
from enum import Enum
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar
from dataclasses import dataclass
import structlog

from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, requests rejected
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes needed to close
    timeout: float = 60.0  # Recovery timeout in seconds
    expected_exception: tuple[type[Exception], ...] = (
        Exception,
    )  # Exceptions that count as failures
    name: str = "default"  # Circuit breaker name for logging


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""

    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0


class CircuitBreaker:
    """
    Circuit Breaker implementation with configurable behavior.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failing state, requests are rejected immediately
    - HALF_OPEN: Testing recovery, limited requests allowed

    Usage:
        breaker = CircuitBreaker(config=CircuitBreakerConfig(name="external_api"))

        @breaker.protect
        async def call_external_api():
            return await external_api_call()
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()
        # Allow only a single probe request while HALF_OPEN
        self._half_open_lock = asyncio.Lock()

    def _distributed_config(self) -> tuple[bool, str]:
        """
        Resolve distributed circuit-breaker settings lazily.

        This avoids forcing settings initialization at import time.
        """
        try:
            from app.shared.core.config import get_settings

            settings = get_settings()
            enabled = bool(
                getattr(settings, "CIRCUIT_BREAKER_DISTRIBUTED_STATE", False)
            )
            prefix = (
                str(
                    getattr(
                        settings,
                        "CIRCUIT_BREAKER_DISTRIBUTED_KEY_PREFIX",
                        "valdrics:circuit",
                    )
                ).strip()
                or "valdrics:circuit"
            )
            return enabled, prefix
        except Exception:
            return False, "valdrics:circuit"

    async def _get_redis_client(self) -> Any | None:
        enabled, _ = self._distributed_config()
        if not enabled:
            return None
        try:
            from app.shared.core.rate_limit import get_redis_client

            return get_redis_client()
        except Exception as exc:
            logger.debug(
                "circuit_breaker_distributed_redis_unavailable",
                name=self.config.name,
                error=str(exc),
            )
            return None

    def _distributed_key(self, suffix: str) -> str:
        _, prefix = self._distributed_config()
        return f"{prefix}:{self.config.name}:{suffix}"

    @staticmethod
    def _as_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.decode(errors="ignore")
        return str(value)

    async def _sync_state_from_distributed(self) -> None:
        redis = await self._get_redis_client()
        if redis is None:
            return

        state_key = self._distributed_key("state")
        failure_key = self._distributed_key("last_failure")
        try:
            state_raw, last_failure_raw = await redis.mget(state_key, failure_key)
            state_text = self._as_text(state_raw)
            if state_text in {
                CircuitState.CLOSED.value,
                CircuitState.OPEN.value,
                CircuitState.HALF_OPEN.value,
            }:
                self.state = CircuitState(state_text)

            last_failure_text = self._as_text(last_failure_raw)
            if last_failure_text:
                self.metrics.last_failure_time = float(last_failure_text)
        except Exception as exc:
            logger.warning(
                "circuit_breaker_distributed_sync_failed",
                name=self.config.name,
                error=str(exc),
            )

    async def _persist_state_to_distributed(self, new_state: CircuitState) -> None:
        redis = await self._get_redis_client()
        if redis is None:
            return

        state_key = self._distributed_key("state")
        failure_key = self._distributed_key("last_failure")
        probe_key = self._distributed_key("half_open_probe")
        try:
            pipeline = redis.pipeline()
            pipeline.set(state_key, new_state.value)
            if new_state == CircuitState.OPEN:
                if self.metrics.last_failure_time is None:
                    self.metrics.last_failure_time = time.time()
                pipeline.set(failure_key, f"{self.metrics.last_failure_time:.6f}")
            elif new_state == CircuitState.CLOSED:
                pipeline.delete(failure_key)
                pipeline.delete(probe_key)
            elif new_state == CircuitState.HALF_OPEN:
                pipeline.delete(probe_key)
            await pipeline.execute()
        except Exception as exc:
            logger.warning(
                "circuit_breaker_distributed_persist_failed",
                name=self.config.name,
                state=new_state.value,
                error=str(exc),
            )

    async def _acquire_distributed_probe(self) -> bool:
        redis = await self._get_redis_client()
        if redis is None:
            return True
        probe_key = self._distributed_key("half_open_probe")
        ttl_seconds = max(1, int(self.config.timeout))
        try:
            acquired = await redis.set(probe_key, "1", ex=ttl_seconds, nx=True)
            return bool(acquired)
        except Exception as exc:
            logger.warning(
                "circuit_breaker_distributed_probe_acquire_failed",
                name=self.config.name,
                error=str(exc),
            )
            return False

    async def _release_distributed_probe(self) -> None:
        redis = await self._get_redis_client()
        if redis is None:
            return
        probe_key = self._distributed_key("half_open_probe")
        try:
            await redis.delete(probe_key)
        except Exception as exc:
            logger.warning(
                "circuit_breaker_distributed_probe_release_failed",
                name=self.config.name,
                error=str(exc),
            )

    async def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.state != CircuitState.OPEN:
            return False

        if self.metrics.last_failure_time is None:
            return True

        return time.time() - self.metrics.last_failure_time >= self.config.timeout

    async def _record_success(self) -> None:
        """Record a successful operation."""
        self.metrics.total_requests += 1
        self.metrics.total_successes += 1
        self.metrics.consecutive_successes += 1
        self.metrics.consecutive_failures = 0
        self.metrics.last_success_time = time.time()

        # Check if we should close the circuit
        if (
            self.state == CircuitState.HALF_OPEN
            and self.metrics.consecutive_successes >= self.config.success_threshold
        ):
            await self._change_state(CircuitState.CLOSED)
            logger.info("circuit_breaker_closed", name=self.config.name)

    async def _record_failure(self, exception: Exception) -> None:
        """Record a failed operation."""
        self.metrics.total_requests += 1
        self.metrics.total_failures += 1
        self.metrics.consecutive_failures += 1
        self.metrics.consecutive_successes = 0
        self.metrics.last_failure_time = time.time()

        # Check if we should open the circuit
        if (
            self.state == CircuitState.CLOSED
            and self.metrics.consecutive_failures >= self.config.failure_threshold
        ):
            await self._change_state(CircuitState.OPEN)
            logger.warning(
                "circuit_breaker_opened",
                name=self.config.name,
                consecutive_failures=self.metrics.consecutive_failures,
                failure_threshold=self.config.failure_threshold,
            )
        elif self.state == CircuitState.HALF_OPEN:
            await self._change_state(CircuitState.OPEN)
            logger.warning("circuit_breaker_half_open_failed", name=self.config.name)

    async def _change_state(self, new_state: CircuitState) -> None:
        """Change circuit breaker state."""
        old_state = self.state
        self.state = new_state
        self.metrics.state_changes += 1
        await self._persist_state_to_distributed(new_state)

        logger.info(
            "circuit_breaker_state_changed",
            name=self.config.name,
            old_state=old_state.value,
            new_state=new_state.value,
            total_requests=self.metrics.total_requests,
            total_failures=self.metrics.total_failures,
        )

    def protect(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Decorator to protect a function with circuit breaker."""

        async def wrapper(*args: Any, **kwargs: Any) -> T:
            probe_lock = None
            distributed_probe_acquired = False
            async with self._lock:
                await self._sync_state_from_distributed()
                # Check if circuit should attempt reset
                if (
                    self.state == CircuitState.OPEN
                    and await self._should_attempt_reset()
                ):
                    await self._change_state(CircuitState.HALF_OPEN)
                    logger.info(
                        "circuit_breaker_attempting_reset", name=self.config.name
                    )

                # Reject request if circuit is open
                if self.state == CircuitState.OPEN:
                    raise ExternalAPIError(
                        f"Circuit breaker is OPEN for {self.config.name}",
                        code="circuit_breaker_open",
                        details={
                            "circuit_name": self.config.name,
                            "state": self.state.value,
                            "last_failure": self.metrics.last_failure_time,
                            "timeout": self.config.timeout,
                        },
                    )

                # Allow only one probe while HALF_OPEN
                if self.state == CircuitState.HALF_OPEN:
                    if self._half_open_lock.locked():
                        raise ExternalAPIError(
                            f"Circuit breaker is HALF_OPEN for {self.config.name}",
                            code="circuit_breaker_half_open",
                            details={
                                "circuit_name": self.config.name,
                                "state": self.state.value,
                                "last_failure": self.metrics.last_failure_time,
                            },
                        )
                    distributed_probe_acquired = await self._acquire_distributed_probe()
                    if not distributed_probe_acquired:
                        raise ExternalAPIError(
                            f"Circuit breaker is HALF_OPEN for {self.config.name}",
                            code="circuit_breaker_half_open",
                            details={
                                "circuit_name": self.config.name,
                                "state": self.state.value,
                                "last_failure": self.metrics.last_failure_time,
                                "reason": "half_open_probe_in_progress",
                            },
                        )
                    await self._half_open_lock.acquire()
                    probe_lock = self._half_open_lock

            try:
                # Execute the protected function
                result = await func(*args, **kwargs)
                await self._record_success()
                return result

            except self.config.expected_exception as e:
                await self._record_failure(e)
                raise
            finally:
                if probe_lock and probe_lock.locked():
                    probe_lock.release()
                if distributed_probe_acquired:
                    await self._release_distributed_probe()

        return wrapper

    async def call(
        self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> T:
        """Call a function with circuit breaker protection."""
        protected_func = self.protect(func)
        return await protected_func(*args, **kwargs)

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring."""
        return {
            "name": self.config.name,
            "state": self.state.value,
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "total_failures": self.metrics.total_failures,
                "total_successes": self.metrics.total_successes,
                "consecutive_failures": self.metrics.consecutive_failures,
                "consecutive_successes": self.metrics.consecutive_successes,
                "last_failure_time": self.metrics.last_failure_time,
                "last_success_time": self.metrics.last_success_time,
                "state_changes": self.metrics.state_changes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            },
        }


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig(name=name)
        _circuit_breakers[name] = CircuitBreaker(config)

    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers for monitoring."""
    return {name: breaker.get_status() for name, breaker in _circuit_breakers.items()}


# Pre-configured circuit breakers for common services
EXTERNAL_API_BREAKER = get_circuit_breaker(
    "external_api",
    CircuitBreakerConfig(
        name="external_api",
        failure_threshold=5,
        success_threshold=2,
        timeout=30.0,
        expected_exception=(ExternalAPIError, asyncio.TimeoutError, ConnectionError),
    ),
)

DATABASE_BREAKER = get_circuit_breaker(
    "database",
    CircuitBreakerConfig(
        name="database",
        failure_threshold=3,
        success_threshold=1,
        timeout=15.0,
        expected_exception=(Exception,),  # Broad exception catching for DB issues
    ),
)

CACHE_BREAKER = get_circuit_breaker(
    "cache",
    CircuitBreakerConfig(
        name="cache",
        failure_threshold=3,
        success_threshold=2,
        timeout=10.0,
        expected_exception=(ConnectionError, asyncio.TimeoutError),
    ),
)
