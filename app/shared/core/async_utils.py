import inspect
from collections.abc import Callable
from typing import Any


async def maybe_await(value: Any) -> Any:
    """Await `value` if it's awaitable, otherwise return it directly.

    This helper allows code that calls library methods which are synchronous
    in production but may be AsyncMocks in tests to behave uniformly.
    """
    if inspect.isawaitable(value):
        return await value
    return value


async def maybe_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call `func` and await the result only when needed.

    Useful for APIs that are synchronous in production but AsyncMock'ed in tests.
    """
    return await maybe_await(func(*args, **kwargs))
