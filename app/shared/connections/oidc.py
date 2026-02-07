from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import async_session_maker
from sqlalchemy import select
from app.shared.core.config import get_settings


from app.models.security import OIDCKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import structlog

logger = structlog.get_logger()

class OIDCService:
    @staticmethod
    async def get_discovery_doc():
        settings = get_settings()
        base_url = settings.API_URL.rstrip("/")
        return {
            "issuer": base_url,
            "jwks_uri": f"{base_url}/oidc/jwks.json",
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "claims_supported": ["sub", "iss", "aud", "iat", "exp", "nbf", "tenant_id"]
        }

    @staticmethod
    async def create_token(tenant_id: str, audience: str, db: Optional[AsyncSession] = None):
        """Create a signed OIDC token for GCP/AWS federated identity."""
        
        settings = get_settings()
        now = datetime.now(timezone.utc)
        
        if db is None:
            async with async_session_maker() as session:
                return await OIDCService._create_token_with_session(tenant_id, audience, session, settings, now)
        else:
            return await OIDCService._create_token_with_session(tenant_id, audience, db, settings, now)

    @staticmethod
    async def _create_token_with_session(tenant_id: str, audience: str, db: AsyncSession, settings, now):
        result = await db.execute(
            select(OIDCKey).where(OIDCKey.is_active).order_by(OIDCKey.created_at.desc())
        )
        key_record = result.scalars().first()
        
        if not key_record:
            from app.shared.core.exceptions import ValdrixException
            raise ValdrixException("No active OIDC key found for signing")
        
        payload = {
            "iss": settings.API_URL.rstrip("/"),
            "sub": f"tenant:{tenant_id}",
            "aud": audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "tenant_id": tenant_id
        }
        
        import jwt
        return jwt.encode(
            payload,
            key_record.private_key_pem,
            algorithm="RS256",
            headers={"kid": key_record.kid}
        )



    @staticmethod
    async def get_jwks(db: Optional[AsyncSession] = None):
        if db is None:
            async with async_session_maker() as session:
                return await OIDCService._get_jwks_with_session(session)
        else:
            return await OIDCService._get_jwks_with_session(db)

    @staticmethod
    async def _get_jwks_with_session(db: AsyncSession):
        result = await db.execute(
            select(OIDCKey).where(OIDCKey.is_active)
        )
        keys = result.scalars().all()
        
        jwks = {"keys": []}
        for k in keys:
            try:
                # Parse PEM and extract RSA components
                pub_key = serialization.load_pem_public_key(
                    k.public_key_pem.encode(),
                    backend=default_backend()
                )
                numbers = pub_key.public_numbers()
                
                # Convert to base64url
                def b64url(n: int):
                    b = n.to_bytes((n.bit_length() + 7) // 8, byteorder='big')
                    return base64.urlsafe_b64encode(b).decode().rstrip('=')
                    
                jwks["keys"].append({
                    "kty": "RSA",
                    "use": "sig",
                    "kid": k.kid,
                    "n": b64url(numbers.n),
                    "e": b64url(numbers.e),
                    "alg": "RS256"
                })
            except Exception:
                continue
        return jwks


    @staticmethod
    async def verify_gcp_access(project_id: str, tenant_id: str) -> tuple[bool, str | None]:
        """Verify that GCP can exchange our OIDC token for access."""
        # This is a placeholder for development; real implementation would call GCP STS
        logger.info("oidc_verify_gcp_access", project_id=project_id, tenant_id=tenant_id)
        return True, None

