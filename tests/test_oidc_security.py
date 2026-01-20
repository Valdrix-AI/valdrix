import pytest
import jwt
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from app.services.connections.oidc import OIDCService
from app.core.config import get_settings

settings = get_settings()

@pytest.mark.asyncio
async def test_oidc_token_claims():
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
async def test_oidc_jwks_structure():
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
async def test_oidc_discovery_doc():
    """
    Verify discovery doc aligns with security profiles.
    """
    doc = await OIDCService.get_discovery_doc()
    
    assert doc["issuer"] == settings.API_URL.rstrip("/")
    assert doc["jwks_uri"].endswith("/oidc/jwks.json")
    assert "RS256" in doc["id_token_signing_alg_values_supported"]
    assert "tenant_id" in doc["claims_supported"]
