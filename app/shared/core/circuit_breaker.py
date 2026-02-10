"""
Circuit Breaker Pattern Implementation

Provides fault tolerance for external service calls with automatic recovery.
Implements the Circuit Breaker pattern to prevent cascade failures.
"""
import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Dict, Union
from dataclasses import dataclass, field
import structlog

from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests rejected
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes needed to close
    timeout: float = 60.0  # Recovery timeout in seconds
    expected_exception: tuple = (Exception,)  # Exceptions that count as failures
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
        if self.state == CircuitState.HALF_OPEN and self.metrics.consecutive_successes >= self.config.success_threshold:
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
        if self.state == CircuitState.CLOSED and self.metrics.consecutive_failures >= self.config.failure_threshold:
            await self._change_state(CircuitState.OPEN)
            logger.warning(
                "circuit_breaker_opened",
                name=self.config.name,
                consecutive_failures=self.metrics.consecutive_failures,
                failure_threshold=self.config.failure_threshold
            )
        elif self.state == CircuitState.HALF_OPEN:
            await self._change_state(CircuitState.OPEN)
            logger.warning("circuit_breaker_half_open_failed", name=self.config.name)

    async def _change_state(self, new_state: CircuitState) -> None:
        """Change circuit breaker state."""
        old_state = self.state
        self.state = new_state
        self.metrics.state_changes += 1

        logger.info(
            "circuit_breaker_state_changed",
            name=self.config.name,
            old_state=old_state.value,
            new_state=new_state.value,
            total_requests=self.metrics.total_requests,
            total_failures=self.metrics.total_failures
        )

    def protect(self, func: Callable) -> Callable:
        """Decorator to protect a function with circuit breaker."""
        async def wrapper(*args, **kwargs):
            probe_lock = None
            async with self._lock:
                # Check if circuit should attempt reset
                if self.state == CircuitState.OPEN and await self._should_attempt_reset():
                    await self._change_state(CircuitState.HALF_OPEN)
                    logger.info("circuit_breaker_attempting_reset", name=self.config.name)

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
                        }
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
                            }
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

        return wrapper

    async def call(self, func: Callable, *args, **kwargs):
        """Call a function with circuit breaker protection."""
        protected_func = self.protect(func)
        return await protected_func(*args, **kwargs)

    def get_status(self) -> Dict[str, Any]:
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
            }
        }


# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig(name=name)
        _circuit_breakers[name] = CircuitBreaker(config)

    return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, Dict[str, Any]]:
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
        expected_exception=(ExternalAPIError, asyncio.TimeoutError, ConnectionError)
    )
)

DATABASE_BREAKER = get_circuit_breaker(
    "database",
    CircuitBreakerConfig(
        name="database",
        failure_threshold=3,
        success_threshold=1,
        timeout=15.0,
        expected_exception=(Exception,)  # Broad exception catching for DB issues
    )
)

CACHE_BREAKER = get_circuit_breaker(
    "cache",
    CircuitBreakerConfig(
        name="cache",
        failure_threshold=3,
        success_threshold=2,
        timeout=10.0,
        expected_exception=(ConnectionError, asyncio.TimeoutError)
    )
)
