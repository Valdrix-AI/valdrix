from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.shared.adapters.http_retry import execute_with_http_retry
from app.shared.core.exceptions import ExternalAPIError


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid")
    return httpx.Response(status_code=status_code, request=request, json={"ok": True})


@pytest.mark.asyncio
async def test_execute_with_http_retry_returns_response_on_first_success() -> None:
    request = AsyncMock(return_value=_response(200))

    response = await execute_with_http_retry(
        request=request,
        url="https://example.invalid",
        max_retries=3,
        retryable_status_codes={500},
        retry_http_status_log_event="retry_http_status",
        retry_transport_log_event="retry_transport",
        status_error_prefix="status failed",
        transport_error_prefix="transport failed",
        retry_sleep_base_seconds=0,
    )

    assert response.status_code == 200
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_execute_with_http_retry_retries_retryable_status_then_succeeds() -> None:
    request = AsyncMock(side_effect=[_response(500), _response(200)])

    with patch("app.shared.adapters.http_retry.asyncio.sleep", new=AsyncMock()) as sleep:
        response = await execute_with_http_retry(
            request=request,
            url="https://example.invalid",
            max_retries=3,
            retryable_status_codes={500},
            retry_http_status_log_event="retry_http_status",
            retry_transport_log_event="retry_transport",
            status_error_prefix="status failed",
            transport_error_prefix="transport failed",
            retry_sleep_base_seconds=0.01,
        )

    assert response.status_code == 200
    assert request.await_count == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_with_http_retry_raises_on_non_retryable_status() -> None:
    request = AsyncMock(return_value=_response(401))

    with pytest.raises(ExternalAPIError, match="status failed with status 401"):
        await execute_with_http_retry(
            request=request,
            url="https://example.invalid",
            max_retries=3,
            retryable_status_codes={500},
            retry_http_status_log_event="retry_http_status",
            retry_transport_log_event="retry_transport",
            status_error_prefix="status failed",
            transport_error_prefix="transport failed",
            retry_sleep_base_seconds=0,
        )

    assert request.await_count == 1


@pytest.mark.asyncio
async def test_execute_with_http_retry_retries_transport_error_then_succeeds() -> None:
    request = AsyncMock(side_effect=[httpx.ConnectError("down"), _response(200)])

    with patch("app.shared.adapters.http_retry.asyncio.sleep", new=AsyncMock()) as sleep:
        response = await execute_with_http_retry(
            request=request,
            url="https://example.invalid",
            max_retries=3,
            retryable_status_codes={500},
            retry_http_status_log_event="retry_http_status",
            retry_transport_log_event="retry_transport",
            status_error_prefix="status failed",
            transport_error_prefix="transport failed",
            retry_sleep_base_seconds=0.01,
        )

    assert response.status_code == 200
    assert request.await_count == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_with_http_retry_raises_unexpected_when_max_retries_zero() -> None:
    request = AsyncMock(return_value=_response(200))

    with pytest.raises(ExternalAPIError, match="transport failed unexpectedly"):
        await execute_with_http_retry(
            request=request,
            url="https://example.invalid",
            max_retries=0,
            retryable_status_codes={500},
            retry_http_status_log_event="retry_http_status",
            retry_transport_log_event="retry_transport",
            status_error_prefix="status failed",
            transport_error_prefix="transport failed",
            retry_sleep_base_seconds=0,
        )

    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_with_http_retry_raises_last_transport_error_after_exhaustion() -> None:
    request = AsyncMock(
        side_effect=[httpx.ConnectError("down-1"), httpx.ConnectError("down-2")]
    )

    with pytest.raises(ExternalAPIError, match="transport failed: down-2"):
        await execute_with_http_retry(
            request=request,
            url="https://example.invalid",
            max_retries=2,
            retryable_status_codes={500},
            retry_http_status_log_event="retry_http_status",
            retry_transport_log_event="retry_transport",
            status_error_prefix="status failed",
            transport_error_prefix="transport failed",
            retry_sleep_base_seconds=0,
        )

    assert request.await_count == 2
