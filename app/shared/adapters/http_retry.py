import asyncio
from collections.abc import Awaitable, Callable

import httpx
import structlog

from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


async def execute_with_http_retry(
    *,
    request: Callable[[], Awaitable[httpx.Response]],
    url: str,
    max_retries: int,
    retryable_status_codes: set[int],
    retry_http_status_log_event: str,
    retry_transport_log_event: str,
    status_error_prefix: str,
    transport_error_prefix: str,
    retry_sleep_base_seconds: float = 0.05,
) -> httpx.Response:
    """
    Execute an HTTP request coroutine with unified retry/error semantics.
    """
    last_error: Exception | None = None
    attempts = max(0, int(max_retries))

    for attempt in range(1, attempts + 1):
        try:
            response = await request()
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            retryable = status_code in retryable_status_codes
            if retryable and attempt < attempts:
                logger.warning(
                    retry_http_status_log_event,
                    attempt=attempt,
                    max_attempts=attempts,
                    status_code=status_code,
                    url=url,
                )
                await asyncio.sleep(retry_sleep_base_seconds * attempt)
                continue
            raise ExternalAPIError(
                f"{status_error_prefix} with status {status_code}: {exc}"
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt < attempts:
                logger.warning(
                    retry_transport_log_event,
                    attempt=attempt,
                    max_attempts=attempts,
                    url=url,
                    error=str(exc),
                )
                await asyncio.sleep(retry_sleep_base_seconds * attempt)
                continue
            raise ExternalAPIError(f"{transport_error_prefix}: {exc}") from exc

    if last_error is not None:
        raise ExternalAPIError(f"{transport_error_prefix}: {last_error}") from last_error
    raise ExternalAPIError(f"{transport_error_prefix} unexpectedly")
