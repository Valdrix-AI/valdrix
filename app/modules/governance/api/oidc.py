"""
OIDC Discovery Router

Exposes the standard OIDC metadata and JWKS endpoints required
for cloud providers to verify Valdrix identity tokens.
"""

from typing import Any, Dict
from fastapi import APIRouter, Request
from app.shared.connections.oidc import OIDCService
from app.shared.core.rate_limit import auth_limit
import structlog

logger = structlog.get_logger()
router = APIRouter(tags=["oidc"])


@router.get("/.well-known/openid-configuration")
@auth_limit
async def oidc_discovery(request: Request) -> Dict[str, Any]:
    """Standard OIDC Discovery document."""
    return await OIDCService.get_discovery_doc()


@router.get("/.well-known/jwks.json")
@auth_limit
async def oidc_jwks(request: Request) -> Dict[str, Any]:
    """Public keys for token verification."""
    return await OIDCService.get_jwks()
