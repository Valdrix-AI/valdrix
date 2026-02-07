import time
import json
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
import structlog

from app.shared.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

# Alias for backward compatibility
CircuitBreakerStateEnum = CircuitState

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 300
    max_daily_savings_usd: float = 1000.0

    @classmethod
    def from_settings(cls):
        s = get_settings()
        return cls(
            failure_threshold=s.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout_seconds=s.CIRCUIT_BREAKER_RECOVERY_SECONDS,
            max_daily_savings_usd=s.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS
        )

class CircuitBreakerState:
    """ Handles state persistence for Circuit Breaker, with Redis fallback to Memory. """
    def __init__(self, tenant_id: str, redis_client=None):
        self.tenant_id = tenant_id
        self.redis = redis_client
        self._memory_state: Dict[str, Any] = {}
        self.prefix = f"cb:{tenant_id}:"

    async def get(self, key: str, default: Any = None) -> Any:
        if self.redis:
            val = await self.redis.get(self.prefix + key)
            if val is not None:
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError, ValueError):
                    return val
            return default
        return self._memory_state.get(key, default)

    async def set(self, key: str, value: Any, expire: int = None):
        if self.redis:
            val = json.dumps(value) if not isinstance(value, (str, bytes)) else value
            await self.redis.set(self.prefix + key, val, ex=expire)
        else:
            self._memory_state[key] = value

    async def incr(self, key: str) -> int:
        if self.redis:
            return await self.redis.incr(self.prefix + key)
        
        current = self._memory_state.get(key, 0)
        new_val = current + 1
        self._memory_state[key] = new_val
        return new_val

    async def delete(self, key: str):
        if self.redis:
            await self.redis.delete(self.prefix + key)
        else:
            self._memory_state.pop(key, None)

class CircuitBreaker:
    """
    Advanced Circuit Breaker with tenant isolation and optional Redis persistence.
    Protects remediation actions from cascading failures.
    """
    def __init__(self, tenant_id: str, config: Optional[CircuitBreakerConfig] = None, redis_client=None):
        self.tenant_id = tenant_id
        self.config = config or CircuitBreakerConfig.from_settings()
        self.state = CircuitBreakerState(tenant_id, redis_client)

    async def get_state(self) -> CircuitState:
        s = await self.state.get("state", CircuitState.CLOSED.value)
        return CircuitState(s)

    async def can_execute(self, estimated_savings: float = 0.0) -> bool:
        state = await self.get_state()
        
        if state == CircuitState.OPEN.value or state == CircuitState.OPEN:
            last_fail = await self.state.get("last_failure_at")
            if last_fail and (time.time() - last_fail) > self.config.recovery_timeout_seconds:
                # Transition to HALF_OPEN
                await self.state.set("state", CircuitState.HALF_OPEN.value)
                logger.info("circuit_breaker_half_open", tenant_id=self.tenant_id)
                return True
            return False
            
        # Check daily budget
        daily_savings = await self.state.get("daily_savings_usd", 0.0)
        if (daily_savings + estimated_savings) > self.config.max_daily_savings_usd:
            logger.warning("circuit_breaker_budget_exceeded", 
                          tenant_id=self.tenant_id, 
                          current=daily_savings, 
                          limit=self.config.max_daily_savings_usd)
            return False
            
        return True

    async def record_success(self, savings: float = 0.0):
        state = await self.get_state()
        if state == CircuitState.HALF_OPEN:
            await self.reset()
            logger.info("circuit_breaker_recovered", tenant_id=self.tenant_id)
        
        # Reset failure count
        await self.state.set("failure_count", 0)
        
        # Track savings (daily budget)
        current_savings = await self.state.get("daily_savings_usd", 0.0)
        await self.state.set("daily_savings_usd", current_savings + savings)

    async def record_failure(self, error: str):
        count = await self.state.incr("failure_count")
        await self.state.set("last_failure_at", time.time())
        await self.state.set("last_error", error)
        
        if count >= self.config.failure_threshold:
            await self.state.set("state", CircuitState.OPEN.value)
            logger.error("circuit_breaker_opened", 
                         tenant_id=self.tenant_id, 
                         failure_count=count, 
                         error=error)

    async def reset(self):
        """ Manually reset the circuit breaker. """
        await self.state.set("state", CircuitState.CLOSED.value)
        await self.state.set("failure_count", 0)
        await self.state.delete("last_failure_at")
        await self.state.delete("last_error")

    async def get_status(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "state": (await self.get_state()).value,
            "failure_count": await self.state.get("failure_count", 0),
            "daily_savings_usd": await self.state.get("daily_savings_usd", 0.0),
            "can_execute": await self.can_execute(),
            "last_error": await self.state.get("last_error")
        }

# Multi-tenant cache
_tenant_breakers: Dict[str, CircuitBreaker] = {}

async def get_circuit_breaker(tenant_id: str) -> CircuitBreaker:
    """ Get or create a circuit breaker for a tenant. """
    if tenant_id not in _tenant_breakers:
        # In a real production environment, we would also inject the Redis client here
        _tenant_breakers[tenant_id] = CircuitBreaker(tenant_id)
    return _tenant_breakers[tenant_id]
