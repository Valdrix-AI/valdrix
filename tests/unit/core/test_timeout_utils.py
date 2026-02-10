import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.shared.core.exceptions import ExternalAPIError
from app.shared.core.timeout import (
    TIMEOUT_CONFIGS,
    TimeoutManager,
    get_timeout_config,
    set_timeout_config,
    timeout_context,
    timeout_operation,
    validate_timeout_config,
)


@pytest.mark.asyncio
async def test_timeout_manager_returns_result():
    manager = TimeoutManager("llm_api")

    async def sample():
        return "ok"

    result = await manager.execute_with_timeout(sample)
    assert result == "ok"


@pytest.mark.asyncio
async def test_timeout_manager_raises_external_api_error_on_timeout():
    manager = TimeoutManager("llm_api")
    manager.config["total"] = 0.001

    async def sample():
        await asyncio.sleep(0.01)
        return "ok"

    with pytest.raises(ExternalAPIError) as exc:
        await manager.execute_with_timeout(sample)

    assert exc.value.code == "timeout_error"
    assert exc.value.details["operation_type"] == "llm_api"
    assert exc.value.details["timeout_seconds"] == manager.config["total"]


def test_validate_timeout_config():
    assert not validate_timeout_config("x", {"total": 1})
    assert not validate_timeout_config("x", {"total": 1, "connect": 0, "read": 1})
    assert validate_timeout_config("x", {"total": 1, "connect": 0.5, "read": 0.5})


def test_set_timeout_config_updates_and_restores():
    original = {k: v.copy() for k, v in TIMEOUT_CONFIGS.items()}
    try:
        new_cfg = {"total": 3.0, "connect": 1.0, "read": 2.0}
        set_timeout_config("custom_test", new_cfg)
        assert TIMEOUT_CONFIGS["custom_test"] == new_cfg
    finally:
        TIMEOUT_CONFIGS.clear()
        TIMEOUT_CONFIGS.update(original)


def test_get_timeout_config_returns_copy():
    cfg = get_timeout_config("llm_api")
    original_total = TIMEOUT_CONFIGS["llm_api"]["total"]
    cfg["total"] = 999
    assert TIMEOUT_CONFIGS["llm_api"]["total"] == original_total


@pytest.mark.asyncio
async def test_timeout_operation_decorator_uses_timeout_manager():
    async def sample(a, b):
        return a + b

    with patch(
        "app.shared.core.timeout.TimeoutManager.execute_with_timeout",
        new_callable=AsyncMock,
        return_value=3,
    ) as mock_exec:
        decorated = timeout_operation("llm_api")(sample)
        result = await decorated(1, 2)

    assert result == 3
    args, _ = mock_exec.call_args
    if args and args[0] is sample:
        assert args[1:] == (1, 2)
    else:
        assert args[1] is sample
        assert args[2:] == (1, 2)


@pytest.mark.asyncio
async def test_timeout_context_allows_custom_timeout():
    async with timeout_context("llm_api", custom_timeout=12.5) as manager:
        assert manager.config["total"] == 12.5
