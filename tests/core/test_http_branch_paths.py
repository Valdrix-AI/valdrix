from __future__ import annotations

from unittest.mock import patch

import pytest

import app.shared.core.http as http_module


@pytest.fixture(autouse=True)
async def _cleanup_clients() -> None:
    await http_module.close_http_client()
    yield
    await http_module.close_http_client()


@pytest.mark.asyncio
async def test_get_http_client_insecure_lazy_initializes_separate_pool() -> None:
    secure_client = http_module.get_http_client(verify=True)
    insecure_client = http_module.get_http_client(verify=False)

    assert secure_client is not insecure_client
    assert insecure_client.is_closed is False


@pytest.mark.asyncio
async def test_init_http_client_warns_when_already_initialized() -> None:
    await http_module.init_http_client()
    with patch("app.shared.core.http.logger.warning") as warning:
        await http_module.init_http_client()
    warning.assert_called_once_with("http_client_already_initialized")


class _SyncCloseClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _NoCloseClient:
    pass


@pytest.mark.asyncio
async def test_close_http_client_handles_sync_close_and_missing_close_methods() -> None:
    sync_client = _SyncCloseClient()
    no_close_client = _NoCloseClient()
    http_module._client = sync_client  # type: ignore[assignment]
    http_module._insecure_client = no_close_client  # type: ignore[assignment]

    await http_module.close_http_client()

    assert sync_client.closed is True
    assert http_module._client is None
    assert http_module._insecure_client is None

