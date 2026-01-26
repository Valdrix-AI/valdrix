import pytest
import jwt
from datetime import datetime, timezone
from uuid import uuid4
from app.shared.connections.oidc import OIDCService
from app.shared.core.config import get_settings

settings = get_settings()

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from app.models.security import OIDCKey
from sqlalchemy.ext.asyncio import AsyncSession

import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def seed_oidc_key(db: AsyncSession):
    """Seed a test RSA key for OIDC tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    key = OIDCKey(
        kid=f"test-kid-{uuid4()}",
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        is_active=True
    )
    db.add(key)
    await db.commit()

@pytest.mark.asyncio
async def test_oidc_token_claims(db: AsyncSession):
    """
    Verify OIDC tokens meet production security standards (nbf, exp, iss).
    """
    tenant_id = str(uuid4())
    audience = "https://iam.googleapis.com/"
    
    token = await OIDCService.create_token(tenant_id, audience)
    
    # Decode without verification to check claims
    decoded = jwt.decode(token, options={"verify_signature": False})
    
    assert decoded["iss"] == settings.API_URL.rstrip("/")
    assert decoded["sub"] == f"tenant:{tenant_id}"
    assert decoded["aud"] == audience
    assert "iat" in decoded
    assert "nbf" in decoded
    assert "exp" in decoded
    assert decoded["tenant_id"] == tenant_id
    
    # Verify expiration is 10 minutes
    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
    assert 9 <= (exp - iat).total_seconds() / 60 <= 11

@pytest.mark.asyncio
async def test_oidc_jwks_structure(db: AsyncSession):
    """
    Verify JWKS contains correctly formatted RSA keys.
    """
    jwks = await OIDCService.get_jwks()
    
    assert "keys" in jwks
    assert len(jwks["keys"]) > 0
    key = jwks["keys"][0]
    
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "kid" in key
    assert "n" in key
    assert "e" in key

@pytest.mark.asyncio
async def test_oidc_discovery_doc(db: AsyncSession):
    """
    Verify discovery doc aligns with security profiles.
    """
    doc = await OIDCService.get_discovery_doc()
    
    assert doc["issuer"] == settings.API_URL.rstrip("/")
    assert doc["jwks_uri"].endswith("/oidc/jwks.json")
    assert "RS256" in doc["id_token_signing_alg_values_supported"]
    assert "tenant_id" in doc["claims_supported"]
