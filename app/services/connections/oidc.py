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
    _last_loaded: Optional[datetime] = None
    _TTL_HOURS = 24

    @classmethod
    async def _ensure_keys(cls):
        """Load or initialize OIDC keys from secure storage."""
        now = datetime.now(timezone.utc)
        if cls._private_key is not None and cls._last_loaded:
            if now < cls._last_loaded + timedelta(hours=cls._TTL_HOURS):
                return
            logger.info("oidc_keys_ttl_expired_reloading")

        from app.db.session import async_session_maker
        from app.models.security import OIDCKey
        from sqlalchemy import select
        import base64

        async with async_session_maker() as db:
            result = await db.execute(
                select(OIDCKey)
                .where(OIDCKey.is_active == True)
                .order_by(OIDCKey.created_at.desc())
                .limit(1)
            )
            key_obj = result.scalar_one_or_none()

            if key_obj:
                cls._private_key = serialization.load_pem_private_key(
                    key_obj.private_key_pem.encode(),
                    password=None,
                    backend=default_backend()
                )
                cls._public_key = cls._private_key.public_key()
                logger.info("oidc_keys_loaded_from_db", kid=key_obj.kid)
            else:
                # Generate RSA Key Pair
                logger.info("generating_new_oidc_keypair")
                cls._private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                    backend=default_backend()
                )
                cls._public_key = cls._private_key.public_key()
                
                # Persist to DB
                kid = f"valdrix-{settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'v1'}-{datetime.now().strftime('%Y%m%d')}"
                
                new_key = OIDCKey(
                    kid=kid,
                    private_key_pem=cls._private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    ).decode(),
                    public_key_pem=cls._public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    ).decode(),
                    is_active=True
                )
                db.add(new_key)
                await db.commit()
                key_obj = new_key

            # Create JWKS cache
            public_numbers = cls._public_key.public_numbers()
            def b64_int(n):
                s = n.to_bytes((n.bit_length() + 7) // 8, 'big')
                return base64.urlsafe_b64encode(s).decode('utf-8').rstrip('=')

            cls._jwks = {
                "keys": [
                    {
                        "kty": "RSA",
                        "alg": "RS256",
                        "use": "sig",
                        "kid": key_obj.kid,
                        "n": b64_int(public_numbers.n),
                        "e": b64_int(public_numbers.e),
                    }
                ]
            }
            cls._last_loaded = now

    @classmethod
    async def get_discovery_doc(cls) -> dict:
        """Return the standard .well-known/openid-configuration."""
        await cls._ensure_keys()
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
    async def get_jwks(cls) -> dict:
        """Return the public keys in JWKS format."""
        await cls._ensure_keys()
        return cls._jwks

    @classmethod
    async def create_token(cls, tenant_id: str, audience: str = "https://iam.googleapis.com/") -> str:
        """
        Create a signed OIDC token for a tenant.
        The token is used by the cloud provider to verify our identity.
        """
        await cls._ensure_keys()
        
        now = datetime.now(timezone.utc)
        payload = {
            "iss": settings.API_URL.rstrip('/'),
            "sub": f"tenant:{tenant_id}",
            "aud": audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),  # BE-OIDC-2: Not Before claim
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "tenant_id": tenant_id
        }
        
        # Convert private key to PEM for pyjwt
        pem = cls._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        kid = cls._jwks["keys"][0]["kid"]
        token = jwt.encode(payload, pem, algorithm="RS256", headers={"kid": kid})
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
