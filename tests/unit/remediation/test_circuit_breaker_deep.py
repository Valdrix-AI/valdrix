import pytest
import time
import json
from unittest.mock import AsyncMock
from app.shared.remediation.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState, get_circuit_breaker

class TestCircuitBreakerDeep:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_circuit_breaker_initial_state(self):
        cb = CircuitBreaker("tenant-1")
        assert await cb.get_state() == CircuitState.CLOSED
        assert await cb.can_execute() is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=60)
        cb = CircuitBreaker("tenant-1", config=config)
        
        await cb.record_failure("error 1")
        assert await cb.get_state() == CircuitState.CLOSED
        
        await cb.record_failure("error 2")
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.can_execute() is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=0.1)
        cb = CircuitBreaker("tenant-1", config=config)
        
        await cb.record_failure("trip")
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.can_execute() is False
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        assert await cb.can_execute() is True
        assert await cb.get_state() == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_success_reset(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("tenant-1", config=config)
        
        await cb.record_failure("trip")
        await cb.state.set("state", CircuitState.HALF_OPEN.value)
        
        await cb.record_success(savings=10.0)
        assert await cb.get_state() == CircuitState.CLOSED
        status = await cb.get_status()
        assert status["daily_savings_usd"] == 10.0

    @pytest.mark.asyncio
    async def test_circuit_breaker_budget_exceeded(self):
        config = CircuitBreakerConfig(max_daily_savings_usd=50.0)
        cb = CircuitBreaker("tenant-1", config=config)
        
        await cb.record_success(savings=40.0)
        assert await cb.can_execute(estimated_savings=20.0) is False
        assert await cb.can_execute(estimated_savings=5.0) is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_redis_persistence(self, mock_redis):
        cb = CircuitBreaker("tenant-1", redis_client=mock_redis)
        
        mock_redis.get.return_value = json.dumps("open")
        mock_redis.incr.return_value = 1
        
        assert await cb.get_state() == CircuitState.OPEN
        
        await cb.record_failure("redis fail")
        assert mock_redis.incr.called
        assert mock_redis.set.called

    @pytest.mark.asyncio
    async def test_circuit_breaker_redis_get_json_fail(self, mock_redis):
        cb = CircuitBreaker("tenant-1", redis_client=mock_redis)
        # Redis returns a string that is not valid JSON
        mock_redis.get.return_value = "invalid-json"
        val = await cb.state.get("key")
        assert val == "invalid-json"

    @pytest.mark.asyncio
    async def test_circuit_breaker_redis_delete(self, mock_redis):
        cb = CircuitBreaker("tenant-1", redis_client=mock_redis)
        await cb.state.delete("key")
        mock_redis.delete.assert_called_with("cb:tenant-1:key")

    @pytest.mark.asyncio
    async def test_circuit_breaker_reset(self):
        cb = CircuitBreaker("tenant-1")
        await cb.record_failure("fail")
        await cb.reset()
        assert await cb.get_state() == CircuitState.CLOSED
        assert await cb.state.get("failure_count") == 0

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_factory(self):
        cb1 = await get_circuit_breaker("t1")
        cb2 = await get_circuit_breaker("t1")
        assert cb1 is cb2
        assert cb1.tenant_id == "t1"
