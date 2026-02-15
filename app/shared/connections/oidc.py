from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import async_session_maker
from sqlalchemy import select
from app.shared.core.config import get_settings


from app.models.security import OIDCKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
import base64
import structlog

logger = structlog.get_logger()


class OIDCService:
    @staticmethod
    async def get_discovery_doc() -> dict[str, Any]:
        """
        Standard OIDC Discovery document.
        Enhanced with recommended fields for AWS/GCP federated identity compatibility.
        """
        settings = get_settings()
        base_url = settings.API_URL.rstrip("/")
        return {
            "issuer": base_url,
            "jwks_uri": f"{base_url}/oidc/jwks.json",
            "authorization_endpoint": f"{base_url}/oidc/auth",  # Placeholder for standard compliance
            "token_endpoint": f"{base_url}/api/v1/public/oidc/token",  # Placeholder for federated exchange
            "scopes_supported": ["openid", "profile", "email"],
            "response_types_supported": ["id_token", "token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "claims_supported": ["sub", "iss", "aud", "iat", "exp", "nbf", "tenant_id"],
        }

    @staticmethod
    async def create_token(
        tenant_id: str,
        audience: str,
        db: Optional[AsyncSession] = None,
    ) -> str:
        """Create a signed OIDC token for GCP/AWS federated identity."""

        settings = get_settings()
        now = datetime.now(timezone.utc)

        if db is None:
            async with async_session_maker() as session:
                return await OIDCService._create_token_with_session(
                    tenant_id, audience, session, settings, now
                )
        else:
            return await OIDCService._create_token_with_session(
                tenant_id, audience, db, settings, now
            )

    @staticmethod
    async def _create_token_with_session(
        tenant_id: str,
        audience: str,
        db: AsyncSession,
        settings: Any,
        now: datetime,
    ) -> str:
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
            "tenant_id": tenant_id,
        }

        import jwt

        return jwt.encode(
            payload,
            key_record.private_key_pem,
            algorithm="RS256",
            headers={"kid": key_record.kid},
        )

    @staticmethod
    async def get_jwks(
        db: Optional[AsyncSession] = None,
    ) -> dict[str, list[dict[str, str]]]:
        if db is None:
            async with async_session_maker() as session:
                return await OIDCService._get_jwks_with_session(session)
        else:
            return await OIDCService._get_jwks_with_session(db)

    @staticmethod
    async def _get_jwks_with_session(
        db: AsyncSession,
    ) -> dict[str, list[dict[str, str]]]:
        result = await db.execute(select(OIDCKey).where(OIDCKey.is_active))
        keys = result.scalars().all()

        jwks: dict[str, list[dict[str, str]]] = {"keys": []}
        for k in keys:
            try:
                # Parse PEM and extract RSA components
                pub_key = serialization.load_pem_public_key(
                    k.public_key_pem.encode(), backend=default_backend()
                )
                if not isinstance(pub_key, rsa.RSAPublicKey):
                    continue
                numbers = pub_key.public_numbers()

                # Convert to base64url
                def b64url(n: int) -> str:
                    b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
                    return base64.urlsafe_b64encode(b).decode().rstrip("=")

                jwks["keys"].append(
                    {
                        "kty": "RSA",
                        "use": "sig",
                        "kid": k.kid,
                        "n": b64url(numbers.n),
                        "e": b64url(numbers.e),
                        "alg": "RS256",
                    }
                )
            except Exception:
                continue
        return jwks

    @staticmethod
    async def verify_gcp_access(
        project_id: str, tenant_id: str
    ) -> tuple[bool, str | None]:
        """Verify that GCP can exchange our OIDC token for access."""
        import httpx

        settings = get_settings()
        audience = settings.GCP_OIDC_AUDIENCE
        if not audience:
            return False, "GCP_OIDC_AUDIENCE is not configured"

        try:
            subject_token = await OIDCService.create_token(
                tenant_id=tenant_id, audience=audience
            )
            payload = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "audience": audience,
                "scope": settings.GCP_OIDC_SCOPE,
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "subject_token": subject_token,
            }

            async with httpx.AsyncClient(
                timeout=settings.GCP_OIDC_VERIFY_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    settings.GCP_OIDC_STS_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code >= 400:
                logger.warning(
                    "oidc_verify_gcp_access_failed",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    status_code=response.status_code,
                )
                try:
                    body = response.json()
                    error_msg = str(
                        body.get("error_description")
                        or body.get("error")
                        or "STS exchange failed"
                    )
                except Exception:
                    error_msg = "STS exchange failed"
                return False, error_msg

            data = response.json()
            if not data.get("access_token"):
                return False, "STS exchange succeeded but no access token returned"

            logger.info(
                "oidc_verify_gcp_access_success",
                project_id=project_id,
                tenant_id=tenant_id,
            )
            return True, None
        except Exception as exc:
            logger.error(
                "oidc_verify_gcp_access_error",
                project_id=project_id,
                tenant_id=tenant_id,
                error=str(exc),
            )
            return False, "Failed to verify GCP access via STS"
