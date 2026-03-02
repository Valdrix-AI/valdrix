import pytest
import httpx
import respx

from app.shared.core.http import get_http_client, init_http_client, close_http_client


@pytest.fixture(autouse=True)
async def cleanup_http_singleton():
    """Ensure a clean singleton state for every test."""
    await close_http_client()
    yield
    await close_http_client()


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


@pytest.mark.asyncio
async def test_http_client_production_settings():
    """Verify that the client is initialized with 2026 production settings."""
    await init_http_client()
    client = get_http_client()

    assert client.timeout.read == 20.0
    assert client.headers["User-Agent"] == "Valdrics-AI/2026.02"

    with respx.mock:
        respx.get("https://www.google.com").mock(return_value=httpx.Response(200))
        response = await client.get("https://www.google.com")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_http_client_lazy_initialization():
    """Verify that get_http_client auto-initializes if init_http_client wasn't called."""
    # This should trigger lazy initialization with default settings
    client = get_http_client()
    assert client is not None
    assert client.timeout.read == 20.0  # Matches lazy-init default in http.py
