import inspect
from typing import Any

async def maybe_await(value: Any) -> Any:
    """Await `value` if it's awaitable, otherwise return it directly.

    This helper allows code that calls library methods which are synchronous
    in production but may be AsyncMocks in tests to behave uniformly.
    """
    if inspect.isawaitable(value):
        return await value
    return value
