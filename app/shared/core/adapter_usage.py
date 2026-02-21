from __future__ import annotations

import inspect
from datetime import date
from typing import Any


async def fetch_daily_costs_if_supported(
    adapter: Any,
    start_date: date,
    end_date: date,
    *,
    group_by_service: bool = True,
) -> Any | None:
    """
    Return daily grouped cost summary when an adapter actually supports it.

    This avoids false positives from dynamic mocks where attribute access
    creates non-awaitable placeholders for unknown methods.
    """
    daily_method = getattr(adapter, "get_daily_costs", None)
    if daily_method is None or not callable(daily_method):
        return None

    result = daily_method(
        start_date,
        end_date,
        group_by_service=group_by_service,
    )

    if inspect.isawaitable(result):
        return await result

    # Allow synchronous implementations that already return a concrete summary object.
    records = getattr(result, "records", None)
    if isinstance(records, list):
        return result

    return None
