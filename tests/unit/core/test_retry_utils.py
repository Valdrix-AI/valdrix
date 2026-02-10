import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.shared.core.retry import (
    RETRY_CONFIGS,
    RetryManager,
    execute_with_deadlock_retry,
    get_retry_config,
    retry_operation,
    tenacity_retry,
)


@pytest.mark.asyncio
async def test_execute_with_retry_succeeds_after_retries():
    manager = RetryManager("database")
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise Exception("fail")
        return "ok"

    with patch("app.shared.core.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep, \
         patch("app.shared.core.retry.random.random", return_value=0.5):
        result = await manager.execute_with_retry(flaky)

    assert result == "ok"
    assert attempts == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_execute_with_retry_raises_after_exhaustion():
    manager = RetryManager("database")

    async def always_fail():
        raise Exception("boom")

    with patch("app.shared.core.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(Exception, match="boom"):
            await manager.execute_with_retry(always_fail)

    assert mock_sleep.await_count == manager.config["max_attempts"] - 1


def test_calculate_backoff_clamped_and_deterministic():
    manager = RetryManager("database")
    manager.config["min_wait"] = 0.1
    manager.config["max_wait"] = 0.2
    manager.config["multiplier"] = 2.0

    with patch("app.shared.core.retry.random.random", return_value=0.5):
        assert manager._calculate_backoff(0) == 0.1
        assert manager._calculate_backoff(10) == 0.2


@pytest.mark.asyncio
async def test_retry_operation_decorator_uses_manager():
    @retry_operation("database")
    async def handler(x):
        return x

    with patch(
        "app.shared.core.retry.RetryManager.execute_with_retry",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_exec:
        result = await handler(123)

    assert result == "ok"
    args, _ = mock_exec.call_args
    assert 123 in args


@pytest.mark.asyncio
async def test_tenacity_retry_success():
    @tenacity_retry("database")
    async def handler():
        return "ok"

    assert await handler() == "ok"


@pytest.mark.asyncio
async def test_execute_with_deadlock_retry_retries():
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise Exception("deadlock detected")
        return "ok"

    with patch("app.shared.core.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep, \
         patch("app.shared.core.retry.random.uniform", return_value=0.0):
        result = await execute_with_deadlock_retry(flaky)

    assert result == "ok"
    assert attempts == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_execute_with_deadlock_retry_non_deadlock_raises():
    async def fail():
        raise Exception("other error")

    with patch("app.shared.core.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(Exception, match="other error"):
            await execute_with_deadlock_retry(fail)

    mock_sleep.assert_not_called()


def test_get_retry_config_returns_copy():
    cfg = get_retry_config("cache")
    cfg["min_wait"] = 999
    assert RETRY_CONFIGS["cache"]["min_wait"] != 999
