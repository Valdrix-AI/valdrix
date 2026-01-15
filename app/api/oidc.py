"""
OIDC Discovery Router

Exposes the standard OIDC metadata and JWKS endpoints required 
for cloud providers to verify Valdrix identity tokens.
"""

from fastapi import APIRouter
from app.services.connections.oidc import OIDCService

router = APIRouter(tags=["oidc"])

@router.get("/.well-known/openid-configuration")
async def get_oidc_config():
    """Standard OIDC Discovery document."""
    return OIDCService.get_discovery_doc()

@router.get("/oidc/jwks.json")
async def get_jwks():
    """Public keys for token verification."""
    return OIDCService.get_jwks()
