import asyncio

import pytest

from app.shared.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ExternalAPIError,
    get_all_circuit_breakers,
    get_circuit_breaker,
    _circuit_breakers,
)


@pytest.fixture(autouse=True)
def reset_registry():
    _circuit_breakers.clear()
    yield
    _circuit_breakers.clear()


@pytest.mark.asyncio
async def test_circuit_opens_after_failures():
    config = CircuitBreakerConfig(name="test", failure_threshold=2, timeout=60.0)
    breaker = CircuitBreaker(config)

    async def fail():
        raise ExternalAPIError("boom")

    protected = breaker.protect(fail)

    with pytest.raises(ExternalAPIError):
        await protected()
    with pytest.raises(ExternalAPIError):
        await protected()

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_circuit_rejects_without_reset():
    config = CircuitBreakerConfig(name="test", failure_threshold=1, timeout=999.0)
    breaker = CircuitBreaker(config)

    async def fail():
        raise ExternalAPIError("boom")

    protected = breaker.protect(fail)

    with pytest.raises(ExternalAPIError):
        await protected()

    with pytest.raises(ExternalAPIError) as exc:
        await protected()

    assert exc.value.code == "circuit_breaker_open"
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_half_open_closes_after_success_threshold():
    config = CircuitBreakerConfig(name="test", failure_threshold=1, success_threshold=2, timeout=0.0)
    breaker = CircuitBreaker(config)

    async def fail():
        raise ExternalAPIError("boom")

    async def ok():
        return "ok"

    protected_fail = breaker.protect(fail)
    protected_ok = breaker.protect(ok)

    with pytest.raises(ExternalAPIError):
        await protected_fail()

    assert breaker.state == CircuitState.OPEN

    result1 = await protected_ok()
    assert result1 == "ok"
    assert breaker.state == CircuitState.HALF_OPEN

    result2 = await protected_ok()
    assert result2 == "ok"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens():
    config = CircuitBreakerConfig(name="test", failure_threshold=1, success_threshold=2, timeout=0.0)
    breaker = CircuitBreaker(config)

    async def fail():
        raise ExternalAPIError("boom")

    protected = breaker.protect(fail)

    with pytest.raises(ExternalAPIError):
        await protected()

    assert breaker.state == CircuitState.OPEN

    with pytest.raises(ExternalAPIError):
        await protected()

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_half_open_allows_single_probe():
    config = CircuitBreakerConfig(name="test", failure_threshold=1, success_threshold=1, timeout=0.0)
    breaker = CircuitBreaker(config)

    async def fail():
        raise ExternalAPIError("boom")

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_ok():
        started.set()
        await release.wait()
        return "ok"

    protected_fail = breaker.protect(fail)
    protected_ok = breaker.protect(slow_ok)

    with pytest.raises(ExternalAPIError):
        await protected_fail()

    task = asyncio.create_task(protected_ok())
    await started.wait()

    with pytest.raises(ExternalAPIError) as exc:
        await protected_ok()

    assert exc.value.code == "circuit_breaker_half_open"

    release.set()
    assert await task == "ok"


def test_get_circuit_breaker_registry():
    config = CircuitBreakerConfig(name="api")
    b1 = get_circuit_breaker("api", config=config)
    b2 = get_circuit_breaker("api")
    assert b1 is b2
    all_status = get_all_circuit_breakers()
    assert "api" in all_status
