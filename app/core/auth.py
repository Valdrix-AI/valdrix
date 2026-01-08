import jwt
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import structlog
from app.core.config import get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.tenant import User

logger = structlog.get_logger()

# HTTPBearer: Extracts "Bearer <token>" from Authorization header
# auto_error=False: Returns None instead of 403 if no token (allows optional auth)
security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """
    Represents the authenticated user from the JWT.
    
    Fields:
    - id: Supabase user UUID (used as PK in our users table)
    - email: User's email from Supabase
    - tenant_id: Will be populated from our database (not in JWT)
    """
    id: UUID
    email: str
    tenant_id: Optional[UUID] = None


def decode_jwt(token: str) -> dict:
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
            algorithms=["HS256", "ES256"],
            audience="authenticated",  # Supabase uses this audience
        )
        return payload
    
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

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    logger.info("user_authenticated", user_id=user_id, email=email)
    return CurrentUser(id=UUID(user_id), email=email)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: AsyncSession = Depends(get_db)) -> CurrentUser:
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

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Fetch user from DB
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    # Handle not found
    if user is None:
      raise HTTPException(403, "User not found. Complete Onboarding first.")
    
    logger.info("user_authenticated", user_id=str(user.id), email=user.email)
    
    return CurrentUser(id=user.id, email=user.email, tenant_id=user.tenant_id)




async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[CurrentUser]:
    """
    Same as get_current_user but returns None instead of 401.
    
    Use for endpoints that work with or without auth:
        @app.get("/public-data")
        async def get_data(user: Optional[CurrentUser] = Depends(get_current_user_optional)):
            if user:
                return private_data
            return public_data
    """
    if credentials is None:
        return None
    
    try:
        payload = decode_jwt(credentials.credentials)
        user_id = payload.get("sub")
        email = payload.get("email")
        
        if not user_id:
            return None
        
        return CurrentUser(id=UUID(user_id), email=email)
    except HTTPException:
        return None







        