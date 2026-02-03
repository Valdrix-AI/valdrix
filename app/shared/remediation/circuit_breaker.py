from typing import Any, Callable, Optional
import time
import asyncio
from enum import Enum
from dataclasses import dataclass
import structlog
from app.shared.core.exceptions import ValdrixException

logger = structlog.get_logger()

class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

# Alias for backward compatibility if needed
CircuitState = CircuitBreakerState

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_time: int = 60
    daily_budget_usd: float = 1000.0

class CircuitBreakerError(ValdrixException):
    def __init__(self, service: str):
        super().__init__(
            message=f"Circuit breaker for {service} is open",
            code="circuit_breaker_open",
            status_code=503
        )

class CircuitBreaker:
    """
    Implementation of the Circuit Breaker pattern to protect the app 
    from cascading failures in external services (like cloud APIs).
    """
    def __init__(
        self,
        service: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.service = service
        self.config = config or CircuitBreakerConfig()
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - (self.last_failure_time or 0) > self.config.recovery_time:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("circuit_breaker_half_open", service=self.service)
            else:
                raise CircuitBreakerError(self.service)

        try:
            # Handle sync functions too if needed, but the interface says async
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info("circuit_breaker_closed", service=self.service)
            
            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.error("circuit_breaker_opened", service=self.service, error=str(e))
            
            raise e

