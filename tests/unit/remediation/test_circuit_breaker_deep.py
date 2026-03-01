import pytest
import time
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch
from app.shared.remediation.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_circuit_breaker,
)
from app.shared.remediation import circuit_breaker as cb_module


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

    @pytest.mark.asyncio
    async def test_daily_savings_resets_when_day_changes(self):
        config = CircuitBreakerConfig(max_daily_savings_usd=50.0)
        cb = CircuitBreaker("tenant-1", config=config)

        await cb.state.set("daily_savings_usd", 40.0)
        await cb.state.set("daily_savings_date", "2000-01-01")

        # Should reset old day usage, otherwise this would exceed 50.0
        assert await cb.can_execute(estimated_savings=20.0) is True

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_eviction_bound(self):
        cb_module._tenant_breakers.clear()
        with patch.object(cb_module.settings, "CIRCUIT_BREAKER_CACHE_SIZE", 2):
            await get_circuit_breaker("tenant-1")
            await get_circuit_breaker("tenant-2")
            await get_circuit_breaker("tenant-3")

            assert len(cb_module._tenant_breakers) == 2
            assert "tenant-1" not in cb_module._tenant_breakers

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_uses_distributed_redis_when_enabled(self):
        cb_module._tenant_breakers.clear()
        redis_client = AsyncMock()

        with patch.object(
            cb_module,
            "_resolve_distributed_redis_client",
            return_value=redis_client,
        ):
            breaker = await get_circuit_breaker("tenant-distributed")

        assert breaker.state.redis is redis_client

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_falls_back_when_redis_client_unavailable(self):
        cb_module._tenant_breakers.clear()

        with patch.object(
            cb_module,
            "_resolve_distributed_redis_client",
            return_value=None,
        ):
            breaker = await get_circuit_breaker("tenant-distributed-fallback")

        assert breaker.state.redis is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_fails_closed_when_backend_unavailable(self):
        cb = CircuitBreaker(
            "tenant-fail-closed",
            backend_unavailable_reason="distributed_state_backend_unavailable",
        )

        assert await cb.can_execute() is False
        await cb.record_success(5.0)
        await cb.record_failure("boom")
        await cb.reset()
        status = await cb.get_status()
        assert status["distributed_backend_available"] is False
        assert status["backend_unavailable_reason"] == "distributed_state_backend_unavailable"

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_marks_backend_unavailable_in_staging(self):
        cb_module._tenant_breakers.clear()
        runtime_settings = SimpleNamespace(
            ENVIRONMENT="staging",
            CIRCUIT_BREAKER_DISTRIBUTED_STATE=True,
            CIRCUIT_BREAKER_CACHE_SIZE=100,
            CIRCUIT_BREAKER_FAILURE_THRESHOLD=3,
            CIRCUIT_BREAKER_RECOVERY_SECONDS=120,
            CIRCUIT_BREAKER_MAX_DAILY_SAVINGS=1000.0,
        )

        with (
            patch.object(cb_module, "get_settings", return_value=runtime_settings),
            patch.object(cb_module, "_resolve_distributed_redis_client", return_value=None),
        ):
            breaker = await get_circuit_breaker("tenant-staging")

        assert breaker.backend_unavailable_reason == "distributed_state_backend_unavailable"
        assert await breaker.can_execute() is False

    def test_resolve_distributed_redis_client_returns_none_when_disabled(self):
        runtime_settings = SimpleNamespace(
            CIRCUIT_BREAKER_DISTRIBUTED_STATE=False,
            REDIS_URL="redis://localhost:6379/0",
        )
        with patch.object(cb_module, "get_settings", return_value=runtime_settings):
            assert cb_module._resolve_distributed_redis_client() is None

    def test_resolve_distributed_redis_client_returns_client_when_enabled(self):
        runtime_settings = SimpleNamespace(
            CIRCUIT_BREAKER_DISTRIBUTED_STATE=True,
            REDIS_URL="redis://localhost:6379/0",
        )
        redis_client = object()
        with (
            patch.object(cb_module, "get_settings", return_value=runtime_settings),
            patch(
                "app.shared.core.rate_limit.get_redis_client",
                return_value=redis_client,
            ),
        ):
            assert cb_module._resolve_distributed_redis_client() is redis_client
