import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_oidc_discovery(async_client: AsyncClient):
    """Test standard OIDC discovery endpoint."""
    mock_discovery = {
        "issuer": "https://auth.valdrix.ai",
        "authorization_endpoint": "https://auth.valdrix.ai/oauth/authorize",
        "token_endpoint": "https://auth.valdrix.ai/oauth/token",
        "jwks_uri": "https://auth.valdrix.ai/.well-known/jwks.json",
    }

    with patch(
        "app.shared.connections.oidc.OIDCService.get_discovery_doc",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = mock_discovery

        response = await async_client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        assert response.json() == mock_discovery


@pytest.mark.asyncio
async def test_jwks_endpoint(async_client: AsyncClient):
    """Test JWKS endpoint."""
    mock_jwks = {
        "keys": [
            {"kty": "RSA", "kid": "test-key-id", "use": "sig", "n": "...", "e": "AQAB"}
        ]
    }

    with patch(
        "app.shared.connections.oidc.OIDCService.get_jwks", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_jwks

        response = await async_client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        assert response.json() == mock_jwks
