from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.shared.core.retry import RetryManager, execute_with_deadlock_retry, set_retry_config


@pytest.mark.asyncio
async def test_execute_with_retry_success_without_prior_retry() -> None:
    manager = RetryManager("cache")

    async def immediate_success() -> str:
        return "ok"

    result = await manager.execute_with_retry(immediate_success)

    assert result == "ok"


@pytest.mark.asyncio
async def test_execute_with_retry_raises_runtime_error_when_no_attempts_configured() -> None:
    manager = RetryManager("cache")
    manager.config["max_attempts"] = 0

    async def unused() -> str:
        return "never"

    with pytest.raises(RuntimeError, match="without captured exception"):
        await manager.execute_with_retry(unused)


@pytest.mark.asyncio
async def test_execute_with_deadlock_retry_logs_on_final_exhaustion() -> None:
    attempts = 0

    async def always_deadlock() -> str:
        nonlocal attempts
        attempts += 1
        raise Exception("serialization failure on row lock")

    with (
        patch("app.shared.core.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        patch("app.shared.core.retry.random.uniform", return_value=0.0),
    ):
        with pytest.raises(Exception, match="serialization failure"):
            await execute_with_deadlock_retry(always_deadlock)

    assert attempts == 5
    assert mock_sleep.await_count == 4


@pytest.mark.asyncio
async def test_execute_with_deadlock_retry_unexpected_exhaustion_guard() -> None:
    async def should_not_run() -> str:
        return "ok"

    with patch("app.shared.core.retry.range", return_value=[], create=True):
        with pytest.raises(RuntimeError, match="Unexpected retry exhaustion"):
            await execute_with_deadlock_retry(should_not_run)


def test_set_retry_config_rejects_missing_required_keys() -> None:
    with pytest.raises(ValueError, match="Invalid retry configuration"):
        set_retry_config("custom", {"max_attempts": 2})


def test_set_retry_config_filters_invalid_exception_entries() -> None:
    with patch("app.shared.core.retry.logger.info") as mock_info:
        set_retry_config(
            "custom_filtered",
            {
                "max_attempts": 4,
                "min_wait": 0.2,
                "max_wait": 1.0,
                "multiplier": 2,
                "exceptions": (ConnectionError, "bad", object()),
            },
        )

    from app.shared.core.retry import RETRY_CONFIGS

    cfg = RETRY_CONFIGS["custom_filtered"]
    assert cfg["max_attempts"] == 4
    assert cfg["min_wait"] == 0.2
    assert cfg["max_wait"] == 1.0
    assert cfg["multiplier"] == 2.0
    assert cfg["exceptions"] == (ConnectionError,)
    mock_info.assert_called_once()


def test_set_retry_config_falls_back_to_exception_for_non_tuple_exceptions() -> None:
    set_retry_config(
        "custom_default_exception",
        {
            "max_attempts": 1,
            "min_wait": 0.1,
            "max_wait": 0.2,
            "multiplier": 1.5,
            "exceptions": [ConnectionError],
        },
    )

    from app.shared.core.retry import RETRY_CONFIGS

    assert RETRY_CONFIGS["custom_default_exception"]["exceptions"] == (Exception,)

