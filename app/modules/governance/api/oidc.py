"""
OIDC Discovery Router

Exposes the standard OIDC metadata and JWKS endpoints required
for cloud providers to verify Valdrix identity tokens.
"""

from typing import Any, Dict
from fastapi import APIRouter
from app.shared.connections.oidc import OIDCService

router = APIRouter(tags=["oidc"])


@router.get("/.well-known/openid-configuration")
async def get_oidc_config() -> Dict[str, Any]:
    """Standard OIDC Discovery document."""
    return await OIDCService.get_discovery_doc()


@router.get("/.well-known/jwks.json")
@router.get("/oidc/jwks.json")
async def get_jwks() -> Dict[str, Any]:
    """Public keys for token verification."""
    return await OIDCService.get_jwks()
