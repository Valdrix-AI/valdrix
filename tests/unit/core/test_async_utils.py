import pytest

from app.shared.core.async_utils import maybe_await


@pytest.mark.asyncio
async def test_maybe_await_returns_value_for_non_awaitable():
    value = {"ok": True}
    result = await maybe_await(value)
    assert result is value


@pytest.mark.asyncio
async def test_maybe_await_awaits_coroutine():
    async def sample():
        return "done"

    result = await maybe_await(sample())
    assert result == "done"
