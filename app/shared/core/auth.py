import jwt
import hashlib
from functools import lru_cache
from typing import Any, Awaitable, Callable, Optional, cast
from uuid import UUID
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import structlog
from app.shared.core.config import get_settings
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.shared.db.session import get_db, set_session_tenant_id
from app.models.tenant import User, UserRole, UserPersona, Tenant
from app.shared.core.pricing import PricingTier, normalize_tier

logger = structlog.get_logger()

__all__ = [
    "CurrentUser",
    "get_current_user",
    "get_current_user_from_jwt",
    "bind_tenant_db_context",
    "get_current_user_with_db_context",
    "requires_role",
    "requires_role_with_db_context",
    "require_tenant_access",
    "UserRole",
    "UserPersona",
    "PricingTier",
]

security = HTTPBearer(auto_error=False)


def _hash_email(email: str | None) -> str | None:
    if not email:
        return None
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def create_access_token(
    data: dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a new JWT token signed with the application secret.
    """
    settings = get_settings()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60)  # Default 1 hour

    # Ensure standard claims
    if "aud" not in to_encode:
        to_encode["aud"] = "authenticated"
    if "iss" not in to_encode:
        to_encode["iss"] = "supabase"

    to_encode.update({"exp": expire})

    if not settings.SUPABASE_JWT_SECRET:
        raise ValueError("SUPABASE_JWT_SECRET is not configured")

    encode_headers: dict[str, str] | None = None
    signing_kid = str(getattr(settings, "JWT_SIGNING_KID", "") or "").strip()
    if signing_kid:
        encode_headers = {"kid": signing_kid}

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SUPABASE_JWT_SECRET,
        algorithm="HS256",
        headers=encode_headers,
    )
    return encoded_jwt


class CurrentUser(BaseModel):
    """
    Represents the authenticated user from the JWT.
    """

    id: UUID
    email: str
    tenant_id: Optional[UUID] = None
    role: UserRole = UserRole.MEMBER
    tier: PricingTier = PricingTier.FREE
    persona: UserPersona = UserPersona.ENGINEERING


def decode_jwt(token: str) -> dict[str, Any]:
    """
    Decode and verify a Supabase JWT token.

    How it works:
    1. Uses SUPABASE_JWT_SECRET to verify signature
    2. Checks expiration time (exp claim)
    3. Returns payload if valid

    Security:
    - HS256 algorithm must match Supabase's signing algorithm
    - Rejects expired tokens automatically
    - Rejects tampered tokens (signature mismatch)

    Raises:
        HTTPException 401 if token is invalid
    """
    settings = get_settings()

    try:
        if not settings.SUPABASE_JWT_SECRET:
            logger.error("jwt_secret_missing_in_decode")
            raise ValueError("Configuration error: Missing JWT secret")

        # Decode with verification
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",  # Supabase uses this audience
        )
        return cast(dict[str, Any], payload)

    except jwt.ExpiredSignatureError:
        logger.warning("jwt_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("jwt_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user_from_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """
    JWT-only auth. No DB lookup. For onboarding."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(credentials.credentials)
    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    logger.info("user_authenticated", user_id=user_id, email_hash=_hash_email(email))
    return CurrentUser(id=UUID(user_id), email=email)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    JWT + DB lookup. For protected routes
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(credentials.credentials)
    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        # Fetch a minimal auth row for the user. Do NOT load the full User ORM entity here:
        # - It couples auth to every newly added column (schema drift during deploy/migration windows).
        # - It forces decryption work (email) even though the JWT already includes the email claim.
        user_uuid = UUID(user_id)

        def _looks_like_schema_mismatch(exc: Exception) -> bool:
            msg = str(exc).lower()
            # asyncpg / psycopg both include "does not exist" for missing columns/tables/types.
            return "does not exist" in msg and any(
                token in msg for token in ("column", "relation", "type")
            )

        async def _fetch_auth_row(include_optional: bool) -> Any:
            cols: list[Any] = [User.id, User.tenant_id, User.role]
            if include_optional:
                # These columns may not exist yet if a deploy happened before migrations ran.
                cols.extend([User.persona, User.is_active])
            # SECH-HAR-13: Validate tenant status during every auth check (Finding #H18)
            cols.extend([Tenant.plan, Tenant.is_deleted])
            stmt = (
                select(*cols)
                .join(Tenant, User.tenant_id == Tenant.id)
                .where(User.id == user_uuid)
            )
            return (await db.execute(stmt)).one_or_none()

        try:
            # We use a nested transaction (savepoint) for the first probe.
            # If it fails due to a schema mismatch, SQLAlchemy/asyncpg will abort
            # only the nested transaction, leaving the main session healthy for the retry.
            async with db.begin_nested():
                row = await _fetch_auth_row(include_optional=True)
            has_optional_cols = True
        except (DBAPIError, Exception) as exc:
            if _looks_like_schema_mismatch(exc):
                logger.warning(
                    "auth_schema_mismatch_optional_cols_retrying", error=str(exc)
                )
                row = await _fetch_auth_row(include_optional=False)
                has_optional_cols = False
            else:
                raise

        # Handle not found
        if row is None:
            logger.error("auth_user_not_found_in_db", user_id=user_id)
            raise HTTPException(403, "User not found. Complete Onboarding first.")

        # Row shape depends on whether optional columns were selected.
        # With optional cols: (id, tenant_id, role, persona, is_active, plan, is_deleted)
        # Without optional cols: (id, tenant_id, role, plan, is_deleted)
        if has_optional_cols:
            _uid, tenant_id, role_value, persona_value, is_active_value, plan, t_is_deleted = row
        else:
            _uid, tenant_id, role_value, plan, t_is_deleted = row
            persona_value = None
            is_active_value = None

        if t_is_deleted:
            logger.warning("auth_tenant_soft_deleted", tenant_id=str(tenant_id), user_id=user_id)
            raise HTTPException(403, "Access denied: Account is deactivated.")

        tier = normalize_tier(plan)
        persona_value = persona_value or UserPersona.ENGINEERING.value
        try:
            persona = UserPersona(persona_value)
        except Exception:
            logger.warning(
                "auth_invalid_user_persona",
                user_id=str(user_uuid),
                persona=persona_value,
            )
            persona = UserPersona.ENGINEERING

        # SCIM deprovisioning / user disable safety.
        if is_active_value is not None and not bool(is_active_value):
            logger.warning("auth_user_disabled", user_id=str(user_uuid))
            raise HTTPException(status_code=403, detail="User account is disabled.")

        # Store in request state for downstream rate limiting and RLS
        request.state.tenant_id = tenant_id
        request.state.user_id = user_uuid
        request.state.tier = tier  # BE-LLM-4: Enable tier-aware rate limiting

        # Propagate RLS context to the database session ASAP, before any tenant-scoped reads.
        await set_session_tenant_id(db, tenant_id)

        # Tenant-scoped SSO enforcement (implemented as domain allowlisting).
        # If configured, restrict access to approved email domains.
        try:
            from app.models.tenant_identity_settings import TenantIdentitySettings

            identity_settings = (
                await db.execute(
                    select(TenantIdentitySettings).where(
                        TenantIdentitySettings.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
            if identity_settings and bool(
                getattr(identity_settings, "sso_enabled", False)
            ):
                allowed_domains = [
                    str(domain).strip().lower()
                    for domain in (
                        getattr(identity_settings, "allowed_email_domains", None) or []
                    )
                    if str(domain).strip()
                ]
                if allowed_domains:
                    email_value = str(email or "")
                    email_domain = (
                        email_value.split("@")[-1].strip().lower()
                        if "@" in email_value
                        else ""
                    )
                    if not email_domain or email_domain not in allowed_domains:
                        logger.warning(
                            "auth_domain_not_allowed",
                            user_id=str(user_uuid),
                            tenant_id=str(tenant_id),
                            email_domain=email_domain,
                        )
                        raise HTTPException(
                            status_code=403,
                            detail="Access denied: email domain is not allowed for this tenant.",
                        )
        except HTTPException:
            raise
        except Exception as exc:
            app_settings = get_settings()
            # Fail closed only in production to avoid silently bypassing tenant SSO enforcement.
            if app_settings.is_production:
                logger.error(
                    "auth_identity_policy_check_failed",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=500,
                    detail="Identity policy enforcement failed. Please contact support.",
                )
            logger.warning("auth_identity_policy_check_skipped", error=str(exc))

        logger.info(
            "user_authenticated",
            user_id=str(user_uuid),
            email_hash=_hash_email(str(email)),
            role=str(role_value),
            tier=tier.value,
        )

        return CurrentUser(
            id=user_uuid,
            email=str(email),
            tenant_id=tenant_id,
            role=role_value,
            tier=tier,
            persona=persona,
        )
    except HTTPException:
        # Re-raise known HTTP exceptions (like 403 User not found)
        raise
    except Exception as e:
        # Avoid leaking internal DB/schema details to clients, but log enough context for operators.
        logger.exception("auth_failed_unexpectedly", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to an internal server error",
        )


async def bind_tenant_db_context(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Ensure DB session tenant context is bound from authenticated user context.

    This provides defense-in-depth for tenant-scoped routes, including test paths
    where request-state based context propagation may be bypassed.
    """
    if user.tenant_id is None:
        return
    await set_session_tenant_id(db, user.tenant_id)


async def get_current_user_with_db_context(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Return authenticated user after binding tenant context on the DB session."""
    if user.tenant_id is not None:
        await set_session_tenant_id(db, user.tenant_id)
    return user


@lru_cache(maxsize=128)
def requires_role(required_role: str) -> Callable[[CurrentUser], CurrentUser]:
    """
    FastAPI dependency for RBAC.

    Usage:
        @router.post("/admin-only")
        async def admin_only(user: CurrentUser = Depends(requires_role("admin"))):
            ...

    Access Levels:
    - owner: full access (super user)
    - admin: configuration and remediation
    - member: read-only cost viewing
    """

    def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Owner bypasses all role checks
        if user.role == UserRole.OWNER:
            return user

        # Check hierarchy
        # owner > admin > member
        role_hierarchy = {UserRole.OWNER: 100, UserRole.ADMIN: 50, UserRole.MEMBER: 10}

        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(UserRole(required_role), 10)

        if user_level < required_level:
            logger.warning(
                "insufficient_permissions",
                user_id=str(user.id),
                user_role=user.role,
                required_role=required_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}",
            )

        return user

    return role_checker


@lru_cache(maxsize=128)
def requires_role_with_db_context(
    required_role: str,
) -> Callable[..., Awaitable[CurrentUser]]:
    """
    Role check + tenant DB context binding.

    Use this dependency for handlers that execute tenant-scoped DB queries.
    """
    role_dependency = requires_role(required_role)

    async def role_checker(
        user: CurrentUser = Depends(role_dependency),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        if user.tenant_id is not None:
            await set_session_tenant_id(db, user.tenant_id)
        return user

    return role_checker


def require_tenant_access(user: CurrentUser = Depends(get_current_user)) -> UUID:
    """
    Ensures that the current user has access to the tenant context.
    Standardizes BE-SEC-02: Strict Tenant Isolation.
    Mandated for all sensitive API routes.
    """
    if not user.tenant_id:
        logger.error("tenant_id_missing_in_user_context", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required. Please complete onboarding.",
        )
    return user.tenant_id
