from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ExternalAPIError,
)


def _breaker(name: str = "distributed") -> CircuitBreaker:
    return CircuitBreaker(CircuitBreakerConfig(name=name, timeout=30.0))


def test_distributed_config_defaults_when_settings_unavailable() -> None:
    breaker = _breaker()
    with patch("app.shared.core.config.get_settings", side_effect=RuntimeError("no settings")):
        enabled, prefix = breaker._distributed_config()
    assert enabled is False
    assert prefix == "valdrix:circuit"


def test_distributed_config_reads_enabled_flag_and_prefix() -> None:
    breaker = _breaker("ops")
    settings = MagicMock()
    settings.CIRCUIT_BREAKER_DISTRIBUTED_STATE = True
    settings.CIRCUIT_BREAKER_DISTRIBUTED_KEY_PREFIX = "tenant:circuit"

    with patch("app.shared.core.config.get_settings", return_value=settings):
        enabled, prefix = breaker._distributed_config()
        key = breaker._distributed_key("state")

    assert enabled is True
    assert prefix == "tenant:circuit"
    assert key == "tenant:circuit:ops:state"


@pytest.mark.asyncio
async def test_get_redis_client_returns_none_when_distributed_disabled() -> None:
    breaker = _breaker()
    with patch.object(breaker, "_distributed_config", return_value=(False, "x")):
        assert await breaker._get_redis_client() is None


@pytest.mark.asyncio
async def test_get_redis_client_handles_dependency_error() -> None:
    breaker = _breaker()
    with (
        patch.object(breaker, "_distributed_config", return_value=(True, "x")),
        patch("app.shared.core.rate_limit.get_redis_client", side_effect=RuntimeError("redis fail")),
    ):
        assert await breaker._get_redis_client() is None


@pytest.mark.asyncio
async def test_sync_state_from_distributed_updates_state_and_last_failure() -> None:
    breaker = _breaker("alpha")
    redis = AsyncMock()
    redis.mget.return_value = [b"half_open", b"123.45"]

    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        await breaker._sync_state_from_distributed()

    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.metrics.last_failure_time == 123.45


@pytest.mark.asyncio
async def test_sync_state_from_distributed_ignores_invalid_state_and_errors() -> None:
    breaker = _breaker("beta")
    redis = AsyncMock()
    redis.mget.return_value = [b"unexpected_state", b"not-a-float"]

    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        await breaker._sync_state_from_distributed()

    assert breaker.state == CircuitState.CLOSED

    redis_error = AsyncMock()
    redis_error.mget.side_effect = RuntimeError("mget fail")
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis_error)):
        await breaker._sync_state_from_distributed()


@pytest.mark.asyncio
async def test_persist_state_to_distributed_covers_open_closed_and_half_open() -> None:
    breaker = _breaker("gamma")
    redis = MagicMock()
    pipeline = MagicMock()
    pipeline.execute = AsyncMock()
    redis.pipeline.return_value = pipeline

    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        # OPEN should set both state and failure key
        breaker.metrics.last_failure_time = None
        with patch("app.shared.core.circuit_breaker.time.time", return_value=99.0):
            await breaker._persist_state_to_distributed(CircuitState.OPEN)
        assert breaker.metrics.last_failure_time == 99.0

        # CLOSED should delete failure/probe keys
        await breaker._persist_state_to_distributed(CircuitState.CLOSED)

        # HALF_OPEN should delete only probe key in addition to state set
        await breaker._persist_state_to_distributed(CircuitState.HALF_OPEN)

    assert pipeline.set.called
    assert pipeline.delete.called
    assert pipeline.execute.await_count == 3


@pytest.mark.asyncio
async def test_acquire_and_release_distributed_probe_paths() -> None:
    breaker = _breaker("probe")

    # No redis available => allow probe.
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=None)):
        assert await breaker._acquire_distributed_probe() is True
        await breaker._release_distributed_probe()

    # Redis available success + failure + error.
    redis = AsyncMock()
    redis.set.return_value = True
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        assert await breaker._acquire_distributed_probe() is True

    redis.set.return_value = False
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        assert await breaker._acquire_distributed_probe() is False

    redis.set.side_effect = RuntimeError("set fail")
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        assert await breaker._acquire_distributed_probe() is False

    redis.delete.side_effect = RuntimeError("delete fail")
    with patch.object(breaker, "_get_redis_client", new=AsyncMock(return_value=redis)):
        await breaker._release_distributed_probe()


@pytest.mark.asyncio
async def test_should_attempt_reset_logic() -> None:
    breaker = _breaker()

    breaker.state = CircuitState.CLOSED
    assert await breaker._should_attempt_reset() is False

    breaker.state = CircuitState.OPEN
    breaker.metrics.last_failure_time = None
    assert await breaker._should_attempt_reset() is True

    breaker.metrics.last_failure_time = 100.0
    with patch("app.shared.core.circuit_breaker.time.time", return_value=120.0):
        assert await breaker._should_attempt_reset() is False
    with patch("app.shared.core.circuit_breaker.time.time", return_value=131.0):
        assert await breaker._should_attempt_reset() is True


@pytest.mark.asyncio
async def test_half_open_rejects_when_distributed_probe_not_acquired() -> None:
    breaker = _breaker()
    breaker.state = CircuitState.HALF_OPEN

    async def _ok() -> str:
        return "ok"

    protected = breaker.protect(_ok)

    with (
        patch.object(breaker, "_sync_state_from_distributed", new=AsyncMock()),
        patch.object(breaker, "_acquire_distributed_probe", new=AsyncMock(return_value=False)),
    ):
        with pytest.raises(ExternalAPIError) as exc:
            await protected()

    assert exc.value.code == "circuit_breaker_half_open"
    assert exc.value.details["reason"] == "half_open_probe_in_progress"


@pytest.mark.asyncio
async def test_call_uses_protect_wrapper() -> None:
    breaker = _breaker()

    async def _ok(value: str) -> str:
        return value

    result = await breaker.call(_ok, "hello")
    assert result == "hello"
