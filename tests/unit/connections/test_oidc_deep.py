import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from app.shared.connections.oidc import OIDCService
from app.models.security import OIDCKey
from app.shared.core.exceptions import ValdricsException

# Generate a small RSA key for testing
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
public_pem = (
    private_key.public_key()
    .public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)


class TestOIDCDeep:
    @pytest.mark.asyncio
    async def test_get_discovery_doc(self):
        with patch("app.shared.connections.oidc.get_settings") as mock_settings:
            mock_settings.return_value.API_URL = "https://api.test.ai"
            doc = await OIDCService.get_discovery_doc()
            assert doc["issuer"] == "https://api.test.ai"
            assert "/.well-known/jwks.json" in doc["jwks_uri"]

    @pytest.mark.asyncio
    @patch("app.shared.connections.oidc.async_session_maker")
    async def test_create_token_no_db_param(self, mock_session_maker):
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        # Mock key record
        key = OIDCKey(
            kid="test-kid", private_key_pem=private_pem, public_key_pem=public_pem
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = key
        mock_session.execute.return_value = mock_result

        with patch("app.shared.connections.oidc.get_settings") as mock_settings:
            mock_settings.return_value.API_URL = "https://api.test.ai"
            token = await OIDCService.create_token("t1", "aud1")

            decoded = jwt.decode(
                token, public_pem, algorithms=["RS256"], audience="aud1"
            )
            assert decoded["iss"] == "https://api.test.ai"
            assert decoded["sub"] == "tenant:t1"
            assert decoded["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_create_token_no_key_found(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("app.shared.connections.oidc.get_settings"):
            with pytest.raises(ValdricsException, match="No active OIDC key found"):
                await OIDCService.create_token("t1", "aud1", db=mock_session)

    @pytest.mark.asyncio
    @patch("app.shared.connections.oidc.async_session_maker")
    async def test_get_jwks_no_db_param(self, mock_session_maker):
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        key = OIDCKey(kid="test-kid", public_key_pem=public_pem)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [key]
        mock_session.execute.return_value = mock_result

        jwks = await OIDCService.get_jwks()
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["kid"] == "test-kid"
        assert jwks["keys"][0]["kty"] == "RSA"

    @pytest.mark.asyncio
    async def test_get_jwks_invalid_key_skip(self):
        mock_session = AsyncMock()
        key = OIDCKey(kid="bad-key", public_key_pem="INVALID PEM")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [key]
        mock_session.execute.return_value = mock_result

        jwks = await OIDCService.get_jwks(db=mock_session)
        assert len(jwks["keys"]) == 0

    @pytest.mark.asyncio
    async def test_verify_gcp_access_requires_audience(self):
        with patch("app.shared.connections.oidc.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MagicMock(GCP_OIDC_AUDIENCE=None)
            success, err = await OIDCService.verify_gcp_access("p1", "t1")
            assert success is False
            assert "GCP_OIDC_AUDIENCE" in err

    @pytest.mark.asyncio
    async def test_verify_gcp_access_success(self):
        settings = MagicMock(
            GCP_OIDC_AUDIENCE="//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/pool/providers/provider",
            GCP_OIDC_SCOPE="https://www.googleapis.com/auth/cloud-platform",
            GCP_OIDC_STS_URL="https://sts.googleapis.com/v1/token",
            GCP_OIDC_VERIFY_TIMEOUT_SECONDS=10,
        )
        with (
            patch("app.shared.connections.oidc.get_settings", return_value=settings),
            patch(
                "app.shared.connections.oidc.OIDCService.create_token",
                new_callable=AsyncMock,
                return_value="id-token",
            ),
            patch("app.shared.core.http.get_http_client") as mock_get_http_client,
        ):
            mock_client = AsyncMock()
            mock_response = MagicMock(status_code=200)
            mock_response.json.return_value = {"access_token": "access-token"}
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_http_client.return_value = mock_client

            success, err = await OIDCService.verify_gcp_access("p1", "t1")
            assert success is True
            assert err is None
