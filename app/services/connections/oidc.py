"""
OIDC Service for Workload Identity Federation

Provides the OIDC Discovery and JWKS documents required for 
AWS, Azure, and GCP to trust Valdrix tokens.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class OIDCService:
    _private_key = None
    _public_key = None
    _jwks = None

    @classmethod
    def _ensure_keys(cls):
        """Generate ephemeral keys if not present (In production, load from secure storage)."""
        if cls._private_key is None:
            # Generate RSA Key Pair
            cls._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            cls._public_key = cls._private_key.public_key()
            
            # Create JWKS
            public_numbers = cls._public_key.public_numbers()
            # Standard OIDC JWKS format
            import base64
            def b64_int(n):
                s = n.to_bytes((n.bit_length() + 7) // 8, 'big')
                return base64.urlsafe_b64encode(s).decode('utf-8').rstrip('=')

            cls._jwks = {
                "keys": [
                    {
                        "kty": "RSA",
                        "alg": "RS256",
                        "use": "sig",
                        "kid": "valdrix-v1",
                        "n": b64_int(public_numbers.n),
                        "e": b64_int(public_numbers.e),
                    }
                ]
            }
            logger.info("oidc_keys_initialized", kid="valdrix-v1")

    @classmethod
    def get_discovery_doc(cls) -> dict:
        """Return the standard .well-known/openid-configuration."""
        cls._ensure_keys()
        base_url = settings.API_URL.rstrip('/')
        return {
            "issuer": base_url,
            "jwks_uri": f"{base_url}/oidc/jwks.json",
            "id_token_signing_alg_values_supported": ["RS256"],
            "subject_types_supported": ["public"],
            "response_types_supported": ["id_token"],
            "claims_supported": ["sub", "aud", "iat", "exp", "tenant_id"]
        }

    @classmethod
    def get_jwks(cls) -> dict:
        """Return the public keys in JWKS format."""
        cls._ensure_keys()
        return cls._jwks

    @classmethod
    def create_token(cls, tenant_id: str, audience: str = "https://iam.googleapis.com/") -> str:
        """
        Create a signed OIDC token for a tenant.
        The token is used by the cloud provider to verify our identity.
        """
        cls._ensure_keys()
        
        now = datetime.now(timezone.utc)
        payload = {
            "iss": settings.API_URL.rstrip('/'),
            "sub": f"tenant:{tenant_id}",
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "tenant_id": tenant_id
        }
        
        # Convert private key to PEM for pyjwt
        pem = cls._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        token = jwt.encode(payload, pem, algorithm="RS256", headers={"kid": "valdrix-v1"})
        return token

    @classmethod
    async def verify_azure_access(cls, tenant_id: str, client_id: str, azure_tenant_id: str) -> tuple[bool, str | None]:
        """Verify Azure Workload Identity trust."""
        # Simulated OIDC swap proof. 
        # In production, we'd exchange our token for an Azure MSAL token here.
        logger.info("verifying_azure_oidc", tenant_id=tenant_id, client_id=client_id)
        return True, None

    @classmethod
    async def verify_gcp_access(cls, tenant_id: str, project_id: str) -> tuple[bool, str | None]:
        """Verify GCP Workload Identity trust."""
        # Simulated OIDC swap proof.
        logger.info("verifying_gcp_oidc", tenant_id=tenant_id, project_id=project_id)
        return True, None
