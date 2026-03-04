from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import Any


def coerce_positive_limit(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(1, normalized)


def system_sweep_tenant_limit(*, get_settings_fn: Any, coerce_positive_limit_fn: Any) -> int:
    settings = get_settings_fn()
    return int(
        coerce_positive_limit_fn(
        getattr(settings, "SCHEDULER_SYSTEM_SWEEP_MAX_TENANTS", 5000),
        default=5000,
    )
    )


def system_sweep_connection_limit(
    *,
    get_settings_fn: Any,
    coerce_positive_limit_fn: Any,
) -> int:
    settings = get_settings_fn()
    return int(
        coerce_positive_limit_fn(
        getattr(settings, "SCHEDULER_SYSTEM_SWEEP_MAX_CONNECTIONS", 5000),
        default=5000,
    )
    )


def cap_scope_items(
    items: Sequence[Any],
    *,
    scope: str,
    limit: int,
    logger: Any,
) -> list[Any]:
    normalized_items = list(items)
    if len(normalized_items) <= limit:
        return normalized_items
    logger.warning(
        "scheduler_scope_capped",
        scope=scope,
        total_items=len(normalized_items),
        capped_items=limit,
        limit=limit,
    )
    return normalized_items[:limit]


@contextmanager
def scheduler_span(
    name: str,
    *,
    tracer: Any,
    **attributes: object,
) -> Generator[None, None, None]:
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is None:
                continue
            if isinstance(value, (str, bool, int, float)):
                span.set_attribute(f"scheduler.{key}", value)
            else:
                span.set_attribute(f"scheduler.{key}", str(value))
        try:
            yield
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
            from opentelemetry.trace import Status, StatusCode

            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@asynccontextmanager
async def open_db_session(
    *,
    async_session_maker_fn: Any,
    mark_session_system_context_fn: Any,
    logger: Any,
    asyncio_module: Any,
    timeout_seconds: float = 10.0,
) -> AsyncGenerator[Any, None]:
    session_cm = async_session_maker_fn()
    if not hasattr(session_cm, "__aenter__") or not hasattr(session_cm, "__aexit__"):
        raise TypeError(
            "async_session_maker() must return an async context manager for AsyncSession"
        )

    try:
        async with asyncio_module.timeout(timeout_seconds):
            async with session_cm as session:
                await mark_session_system_context_fn(session)
                yield session
    except asyncio_module.TimeoutError as exc:
        logger.error("db_session_acquisition_failed", error=str(exc), type="TimeoutError")
        raise
