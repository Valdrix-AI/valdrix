import pytest
from uuid import uuid4
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from app.shared.connections.oidc import OIDCService
from app.models.security import OIDCKey


@pytest.fixture
def rsa_keys():
    """Generate a real RSA key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


@pytest.mark.asyncio
async def test_get_discovery_doc():
    """Test discovery document generation."""
    doc = await OIDCService.get_discovery_doc()
    assert "issuer" in doc
    assert "jwks_uri" in doc
    assert "authorization_endpoint" in doc
    assert "token_endpoint" in doc
    assert "scopes_supported" in doc
    assert "claims_supported" in doc
    assert "tenant_id" in doc["claims_supported"]


@pytest.mark.asyncio
async def test_get_jwks(db, rsa_keys):
    """Test JWKS generation from DB keys."""
    private_pem, public_pem = rsa_keys
    kid = f"test-key-{uuid4().hex[:8]}"

    # 1. Add key to DB
    key_record = OIDCKey(
        kid=kid,
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(key_record)
    await db.commit()

    # 2. Get JWKS
    jwks = await OIDCService.get_jwks(db=db)

    assert "keys" in jwks
    assert len(jwks["keys"]) >= 1

    target_key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    assert target_key is not None
    assert target_key["kty"] == "RSA"
    assert target_key["use"] == "sig"
    assert target_key["alg"] == "RS256"
    assert "n" in target_key
    assert "e" in target_key


@pytest.mark.asyncio
async def test_create_token(db, rsa_keys):
    """Test OIDC token creation and signing."""
    private_pem, public_pem = rsa_keys
    kid = f"test-key-{uuid4().hex[:8]}"
    tenant_id = str(uuid4())
    audience = "https://gcp.example.com"

    # 1. Add key to DB
    key_record = OIDCKey(
        kid=kid,
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(key_record)
    await db.commit()

    # 2. Create token
    token = await OIDCService.create_token(
        tenant_id=tenant_id, audience=audience, db=db
    )
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    # 3. Decode and verify payload
    import jwt

    payload = jwt.decode(token, public_pem, algorithms=["RS256"], audience=audience)

    assert payload["iss"] is not None
    assert payload["sub"] == f"tenant:{tenant_id}"
    assert payload["tenant_id"] == tenant_id
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]


@pytest.mark.asyncio
async def test_create_token_no_key(db):
    """Test error handling when no key is found."""
    # Ensure no active keys
    from app.shared.core.exceptions import ValdrixException

    tenant_id = str(uuid4())

    with pytest.raises(ValdrixException, match="No active OIDC key found"):
        await OIDCService.create_token(tenant_id=tenant_id, audience="test", db=db)
