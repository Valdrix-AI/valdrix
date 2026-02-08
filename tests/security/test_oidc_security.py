import pytest
import jwt
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from app.shared.connections.oidc import OIDCService
from sqlalchemy import select
from app.models.security import OIDCKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

@pytest.fixture(autouse=True)
async def seed_oidc_key(db):
    """Seed an OIDC key for tests that use the real DB."""
    # Check if one exists
    from sqlalchemy import select
    result = await db.execute(select(OIDCKey).where(OIDCKey.is_active))
    if result.scalars().first():
        return
        
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    oidc_key = OIDCKey(
        kid=f"test-kid-{uuid.uuid4().hex[:4]}",
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(oidc_key)
    await db.commit()
    await db.refresh(oidc_key)
    return oidc_key

@pytest.mark.asyncio
async def test_oidc_discovery(async_client):
    response = await async_client.get("/.well-known/openid-configuration")
    assert response.status_code == 200
    assert "jwks_uri" in response.json()

@pytest.mark.asyncio
async def test_oidc_jwks(async_client):
    response = await async_client.get("/oidc/jwks.json")
    assert response.status_code == 200
    assert "keys" in response.json()

@pytest.mark.asyncio
async def test_oidc_token_creation(db):
    token = await OIDCService.create_token(tenant_id="test-tenant", audience="test-aud", db=db)
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["sub"] == "tenant:test-tenant"
    assert decoded["aud"] == "test-aud"

@pytest.mark.asyncio
async def test_oidc_no_active_keys(db):
    from app.shared.core.exceptions import ValdrixException
    # Use AsyncMock for execute to handle 'await'
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock) as mock_exec:
        # Mock the result to return no keys
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_exec.return_value = mock_result
        
        with pytest.raises(ValdrixException, match="No active OIDC key"):
            await OIDCService.create_token("t1", "a1", db=db)

@pytest.mark.asyncio
async def test_oidc_jwks_matches_seeded_key(db):
    response = await OIDCService.get_jwks(db=db)
    assert len(response["keys"]) > 0
    assert response["keys"][0]["kty"] == "RSA"

@pytest.mark.asyncio
async def test_oidc_create_token_no_db(async_client):
    with patch("jwt.encode", return_value="fake-token"):
        token = await OIDCService.create_token("t1", "a1")
        assert token == "fake-token"

@pytest.mark.asyncio
async def test_oidc_get_jwks_no_db(async_client):
    jwks = await OIDCService.get_jwks()
    assert "keys" in jwks

@pytest.mark.asyncio
async def test_oidc_get_jwks_exception_handling():
    """Test error handling in jwks generation."""
    mock_key = MagicMock()
    mock_key.public_key_pem = "INVALID_PEM"
    mock_key.kid = "k1"
    
    db = MagicMock()
    db.execute = AsyncMock()
    # Mock result and scalars to return our list of keys
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_key]
    db.execute.return_value = mock_result
    
    jwks = await OIDCService.get_jwks(db=db)
    assert jwks == {"keys": []}

@pytest.mark.asyncio
async def test_oidc_verify_gcp():
    success, error = await OIDCService.verify_gcp_access("proj", "tenant")
    assert success is True
    assert error is None

@pytest.mark.asyncio
async def test_oidc_token_expired(db):
    from datetime import timedelta
    # Create a token that expired 1 hour ago
    with patch("app.shared.connections.oidc.datetime") as mock_datetime:
        real_now = datetime.now(timezone.utc)
        mock_now = real_now - timedelta(hours=1)
        mock_datetime.now.return_value = mock_now
        token = await OIDCService.create_token("t1", "a1", db=db)
    
    # Try to decode with verification - should raise ExpiredSignatureError
    pub_key_pem = (await db.execute(select(OIDCKey).where(OIDCKey.is_active))).scalars().first().public_key_pem
    
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, pub_key_pem, algorithms=["RS256"], audience="a1")

@pytest.mark.asyncio
async def test_oidc_token_invalid_signature(db):
    token = await OIDCService.create_token("t1", "a1", db=db)
    
    # Generate a DIFFERENT key to try and verify
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    # Actually public key format
    other_pub_pem = other_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other_pub_pem, algorithms=["RS256"], audience="a1")

@pytest.mark.asyncio
async def test_oidc_token_tampered_payload(db):
    token = await OIDCService.create_token("t1", "a1", db=db)
    header, payload, signature = token.split(".")
    
    # Tamper with the payload
    import base64
    import json
    decoded_payload = json.loads(base64.urlsafe_b64decode(payload + "==").decode())
    decoded_payload["tenant_id"] = "attacker-tenant"
    tampered_payload = base64.urlsafe_b64encode(json.dumps(decoded_payload).encode()).decode().rstrip("=")
    
    tampered_token = f"{header}.{tampered_payload}.{signature}"
    pub_key_pem = (await db.execute(select(OIDCKey).where(OIDCKey.is_active))).scalars().first().public_key_pem
    
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(tampered_token, pub_key_pem, algorithms=["RS256"], audience="a1")
