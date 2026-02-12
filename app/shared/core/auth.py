import jwt
import hashlib
from functools import lru_cache
from typing import Any, Callable, Optional, cast
from uuid import UUID
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import structlog
from app.shared.core.config import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.shared.db.session import get_db, set_session_tenant_id
from app.models.tenant import User, UserRole, Tenant
from app.shared.core.pricing import PricingTier, normalize_tier

logger = structlog.get_logger()

security = HTTPBearer(auto_error=False)

def _hash_email(email: str | None) -> str | None:
    if not email:
        return None
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]

def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate a new JWT token signed with the application secret.
    """
    settings = get_settings()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60) # Default 1 hour
    
    # Ensure standard claims
    if "aud" not in to_encode:
        to_encode["aud"] = "authenticated"
    if "iss" not in to_encode:
        to_encode["iss"] = "supabase"
        
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
    return encoded_jwt


class CurrentUser(BaseModel):
    """
    Represents the authenticated user from the JWT.
    """
    id: UUID
    email: str
    tenant_id: Optional[UUID] = None
    role: UserRole = UserRole.MEMBER
    tier: PricingTier = PricingTier.FREE_TRIAL


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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> CurrentUser:
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
    db: AsyncSession = Depends(get_db)
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

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        # Fetch user and tenant from DB
        result = await db.execute(
            select(User, Tenant.plan)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(User.id == UUID(user_id))
        )
        row = result.one_or_none()

        # Handle not found
        if row is None:
            logger.error("auth_user_not_found_in_db", user_id=user_id)
            raise HTTPException(403, "User not found. Complete Onboarding first.")

        user, plan = row
        tier = normalize_tier(plan)

        # Store in request state for downstream rate limiting and RLS
        request.state.tenant_id = user.tenant_id
        request.state.user_id = user.id
        request.state.tier = tier  # BE-LLM-4: Enable tier-aware rate limiting

        # Propagate RLS context to the database session
        await set_session_tenant_id(db, user.tenant_id)

        logger.info(
            "user_authenticated",
            user_id=str(user.id),
            email_hash=_hash_email(user.email),
            role=user.role,
            tier=tier.value
        )

        return CurrentUser(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            role=user.role,
            tier=tier
        )
    except HTTPException:
        # Re-raise known HTTP exceptions (like 403 User not found)
        raise
    except Exception as e:
        logger.error("auth_failed_unexpectedly", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to an internal server error"
        )








@lru_cache()
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
        role_hierarchy = {
            UserRole.OWNER: 100, 
            UserRole.ADMIN: 50, 
            UserRole.MEMBER: 10
        }

        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(UserRole(required_role), 10)

        if user_level < required_level:
            logger.warning(
                "insufficient_permissions",
                user_id=str(user.id),
                user_role=user.role,
                required_role=required_role
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}"
            )

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
            detail="Tenant context required. Please complete onboarding."
        )
    return user.tenant_id


