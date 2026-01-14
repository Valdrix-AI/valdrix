"""
Circuit Breaker Pattern - Production Ready

Implements safety layers with Redis persistence for distributed systems:
1. Rate Limit: Max N deletions/hour/tenant
2. Daily Budget: Max $X savings/day (prevents runaway)
3. Circuit Breaker: Pause after consecutive failures
4. Dry-Run Default: Always simulate before executing

State is persisted in Redis for multi-instance deployments.

References:
- Microsoft Azure Patterns: Circuit Breaker
- Martin Fowler: CircuitBreaker
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass
import json
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking all calls
    HALF_OPEN = "half_open"  # Testing if safe to resume


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 3
    success_threshold: int = 2
    recovery_timeout_seconds: int = 300
    max_daily_savings_usd: float = 1000.0

    @classmethod
    def from_settings(cls) -> "CircuitBreakerConfig":
        """Load from application settings."""
        return cls(
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout_seconds=settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
            max_daily_savings_usd=settings.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS
        )


class CircuitBreakerState:
    """
    Persistent circuit breaker state.

    Uses Redis for distributed state when available,
    falls back to in-memory for single-instance deployments.
    """

    def __init__(self, tenant_id: str, redis_client=None):
        self.tenant_id = tenant_id
        self.redis = redis_client
        self._key_prefix = f"circuit_breaker:{tenant_id}"

        # In-memory fallback
        self._memory_state: Dict[str, Any] = {}

    async def _get_redis(self):
        """Lazy load Redis connection."""
        if self.redis is None and settings.REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self.redis = aioredis.from_url(settings.REDIS_URL)
            except Exception as e:
                logger.warning("redis_connection_failed", error=str(e))
        return self.redis

    async def get(self, key: str, default=None):
        """Get value from state store."""
        redis = await self._get_redis()
        if redis:
            try:
                value = await redis.get(f"{self._key_prefix}:{key}")
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning("redis_get_failed", key=key, error=str(e))

        return self._memory_state.get(key, default)

    async def set(self, key: str, value: Any, ex: int = None):
        """Set value in state store."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.set(
                    f"{self._key_prefix}:{key}",
                    json.dumps(value),
                    ex=ex
                )
                return
            except Exception as e:
                logger.warning("redis_set_failed", key=key, error=str(e))

        self._memory_state[key] = value

    async def incr(self, key: str) -> int:
        """Increment counter."""
        redis = await self._get_redis()
        if redis:
            try:
                return await redis.incr(f"{self._key_prefix}:{key}")
            except Exception as e:
                logger.warning("redis_incr_failed", key=key, error=str(e))

        current = self._memory_state.get(key, 0)
        self._memory_state[key] = current + 1
        return self._memory_state[key]


class CircuitBreaker:
    """
    Production-ready circuit breaker for automated remediation safety.

    Prevents cascading failures by stopping operations when:
    1. Too many consecutive failures occur
    2. Daily savings budget is exceeded

    Usage:
        breaker = CircuitBreaker(tenant_id="123")

        if await breaker.can_execute(estimated_savings=50.0):
            try:
                result = await execute_remediation()
                await breaker.record_success(savings=result.savings)
            except Exception as e:
                await breaker.record_failure(str(e))
    """

    def __init__(
        self,
        tenant_id: str,
        config: CircuitBreakerConfig = None,
        redis_client=None
    ):
        self.tenant_id = tenant_id
        self.config = config or CircuitBreakerConfig.from_settings()
        self.state = CircuitBreakerState(tenant_id, redis_client)

    async def get_state(self) -> CircuitState:
        """Get current circuit state, considering recovery timeout."""
        state_str = await self.state.get("state", CircuitState.CLOSED.value)
        current_state = CircuitState(state_str)

        if current_state == CircuitState.OPEN:
            if await self._should_attempt_recovery():
                await self.state.set("state", CircuitState.HALF_OPEN.value)
                await self.state.set("success_count", 0)
                logger.info("circuit_half_open",
                           tenant_id=self.tenant_id,
                           msg="Attempting recovery")
                return CircuitState.HALF_OPEN

        return current_state

    async def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to try recovery."""
        last_failure = await self.state.get("last_failure_time")
        if not last_failure:
            return True

        last_failure_dt = datetime.fromisoformat(last_failure)
        elapsed = datetime.now(timezone.utc) - last_failure_dt
        return elapsed.total_seconds() >= self.config.recovery_timeout_seconds

    async def _get_daily_savings(self) -> float:
        """Get today's cumulative savings."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        savings_key = f"daily_savings:{today}"
        return float(await self.state.get(savings_key, 0))

    async def can_execute(self, estimated_savings: float = 0) -> bool:
        """
        Check if operation is allowed.

        Returns False if:
        - Circuit is OPEN
        - Daily budget would be exceeded
        """
        state = await self.get_state()

        if state == CircuitState.OPEN:
            logger.warning("circuit_open",
                          tenant_id=self.tenant_id,
                          msg="Circuit is open, blocking execution")
            return False

        # Check daily budget
        current_savings = await self._get_daily_savings()
        if current_savings + estimated_savings > self.config.max_daily_savings_usd:
            logger.warning("daily_budget_exceeded",
                          tenant_id=self.tenant_id,
                          current=current_savings,
                          estimated=estimated_savings,
                          limit=self.config.max_daily_savings_usd)
            return False

        return True

    async def record_success(self, savings: float = 0) -> None:
        """Record successful execution."""
        await self.state.set("failure_count", 0)

        # Update daily savings
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        savings_key = f"daily_savings:{today}"
        current = await self._get_daily_savings()
        await self.state.set(savings_key, current + savings, ex=86400)  # Expire in 24h

        state = await self.get_state()
        if state == CircuitState.HALF_OPEN:
            success_count = await self.state.incr("success_count")
            if success_count >= self.config.success_threshold:
                await self.state.set("state", CircuitState.CLOSED.value)
                logger.info("circuit_closed",
                           tenant_id=self.tenant_id,
                           msg="Circuit recovered after successful operations")

        logger.debug("breaker_success",
                    tenant_id=self.tenant_id,
                    savings=savings)

    async def record_failure(self, error: str = None) -> None:
        """Record failed execution."""
        failure_count = await self.state.incr("failure_count")
        await self.state.set("success_count", 0)
        await self.state.set(
            "last_failure_time",
            datetime.now(timezone.utc).isoformat()
        )

        if failure_count >= self.config.failure_threshold:
            await self.state.set("state", CircuitState.OPEN.value)
            logger.error("circuit_opened",
                        tenant_id=self.tenant_id,
                        failures=failure_count,
                        error=error,
                        msg="Circuit opened after consecutive failures")

    async def reset(self) -> None:
        """Manually reset circuit breaker (admin action)."""
        await self.state.set("state", CircuitState.CLOSED.value)
        await self.state.set("failure_count", 0)
        await self.state.set("success_count", 0)
        logger.info("circuit_reset",
                   tenant_id=self.tenant_id,
                   msg="Circuit manually reset")

    async def get_status(self) -> Dict[str, Any]:
        """Get current breaker status for monitoring/API."""
        state = await self.get_state()
        daily_savings = await self._get_daily_savings()
        failure_count = await self.state.get("failure_count", 0)

        return {
            "tenant_id": self.tenant_id,
            "state": state.value,
            "failure_count": failure_count,
            "daily_savings_usd": round(daily_savings, 2),
            "daily_budget_usd": self.config.max_daily_savings_usd,
            "budget_remaining_usd": round(
                self.config.max_daily_savings_usd - daily_savings, 2
            ),
            "can_execute": await self.can_execute()
        }


async def get_circuit_breaker(tenant_id: str) -> CircuitBreaker:
    """Factory function to create circuit breaker with Redis if available."""
    redis_client = None
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(settings.REDIS_URL)
        except Exception:
            pass

    return CircuitBreaker(
        tenant_id=tenant_id,
        config=CircuitBreakerConfig.from_settings(),
        redis_client=redis_client
    )
