import pytest
import httpx
from app.shared.core.http import get_http_client, init_http_client, close_http_client


@pytest.mark.asyncio
async def test_http_client_singleton():
    """Verify that get_http_client returns the same instance (singleton)."""
    await init_http_client()
    client1 = get_http_client()
    client2 = get_http_client()

    assert client1 is client2
    assert isinstance(client1, httpx.AsyncClient)
    assert client1.is_closed is False

    await close_http_client()
    # After close, _client should be None.
    # Calling get_http_client again will lazy-init it.
    client3 = get_http_client()
    assert client3 is not client1
    assert client3.is_closed is False
    await close_http_client()


@pytest.mark.asyncio
async def test_http_client_production_settings():
    """Verify that the client is initialized with 2026 production settings."""
    await init_http_client()
    client = get_http_client()

    # Check http2
    # Note: httpx doesn't always expose http2 attribute directly on client in a simple way
    # but we can check the headers or internal state if needed.
    # For now, we check the user agent we set.
    # Check timeout
    assert client.timeout.read == 20.0
    assert client.headers["User-Agent"] == "Valdrix-AI/2026.02"

    # Check limits via transport (if accessible and stable)
    # We can at least verify the client is functional
    response = await client.get("https://www.google.com")
    assert response.status_code == 200

    await close_http_client()


@pytest.mark.asyncio
async def test_http_client_lazy_initialization():
    """Verify that get_http_client auto-initializes if init_http_client wasn't called."""
    await close_http_client()  # Ensure clean state

    # This should trigger lazy initialization with default settings
    client = get_http_client()
    assert client is not None
    assert client.timeout.read == 10.0  # Default in lazy init

    await close_http_client()
