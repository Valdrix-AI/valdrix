from dataclasses import dataclass
from enum import Enum
import structlog
from typing import Optional, Dict
from app.shared.core.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 300
    max_daily_savings_usd: float = 1000.0

class CircuitBreakerState:
    """Handles persistence for CircuitBreaker state (Memory or Redis)."""
    def __init__(self, tenant_id: str, redis_client=None):
        self.tenant_id = tenant_id
        self._data = {}

    async def get(self, key: str, default=None):
        return self._data.get(key, default)

    async def set(self, key: str, value):
        self._data[key] = value

    async def incr(self, key: str):
        val = self._data.get(key, 0) + 1
        self._data[key] = val
        return val

class CircuitBreaker:
    """Remediation Safety Circuit Breaker."""
    def __init__(self, tenant_id: str, config: CircuitBreakerConfig = None):
        self.tenant_id = tenant_id
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState(tenant_id)

    async def get_state(self) -> CircuitState:
        val = await self.state.get("state", CircuitState.CLOSED.value)
        return CircuitState(val)

    async def can_execute(self, estimated_savings: float = 0) -> bool:
        state = await self.get_state()
        if state == CircuitState.OPEN:
            return False
        # Budget check logic would go here
        return True

    async def record_success(self, savings: float = 0):
        await self.state.set("failure_count", 0)
        # Record savings in daily budget

    async def record_failure(self, error: str):
        count = await self.state.incr("failure_count")
        if count >= self.config.failure_threshold:
            await self.state.set("state", CircuitState.OPEN.value)

    async def reset(self):
        await self.state.set("state", CircuitState.CLOSED.value)
        await self.state.set("failure_count", 0)

    async def get_status(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "state": (await self.get_state()).value,
            "failure_count": await self.state.get("failure_count", 0),
            "daily_savings_usd": 0.0,
            "can_execute": await self.can_execute()
        }
