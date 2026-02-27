from __future__ import annotations

import pytest

from app.shared.core.timeout import (
    TIMEOUT_CONFIGS,
    TimeoutManager,
    set_timeout_config,
    timeout_context,
)


@pytest.mark.asyncio
async def test_timeout_manager_re_raises_generic_exceptions() -> None:
    manager = TimeoutManager("default")

    async def fail() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await manager.execute_with_timeout(fail)


@pytest.mark.asyncio
async def test_timeout_context_without_custom_timeout_keeps_default_total() -> None:
    expected_total = TIMEOUT_CONFIGS["llm_api"]["total"]
    async with timeout_context("llm_api") as manager:
        assert manager.config["total"] == expected_total


@pytest.mark.asyncio
async def test_timeout_context_propagates_exceptions() -> None:
    with pytest.raises(RuntimeError, match="context failure"):
        async with timeout_context("cache"):
            raise RuntimeError("context failure")


def test_set_timeout_config_rejects_invalid_config() -> None:
    with pytest.raises(ValueError, match="Invalid timeout configuration"):
        set_timeout_config("invalid", {"total": 1, "connect": 0, "read": 1})
