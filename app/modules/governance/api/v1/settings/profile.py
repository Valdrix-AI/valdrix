"""
User Profile Settings API

Today this is intentionally small: persona preference only.

Persona is a UX default (navigation + default widgets), not a permission boundary.
RBAC + tier gating remain the security/entitlement mechanisms.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import User, UserPersona, UserRole
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.shared.core.auth import CurrentUser, get_current_user, get_current_user_with_db_context
from app.shared.core.pricing import PricingTier
from app.shared.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Profile"])


class ProfileResponse(BaseModel):
    email: str
    role: UserRole
    tier: PricingTier
    persona: UserPersona

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdateRequest(BaseModel):
    persona: UserPersona


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get(
        "x-real-ip"
    )
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        return candidate or None
    if request.client:
        return request.client.host
    return None


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
) -> ProfileResponse:
    # We rely on the DB-backed auth path, which already loads tenant plan and persona.
    return ProfileResponse(
        email=current_user.email,
        role=current_user.role,
        tier=current_user.tier,
        persona=current_user.persona,
    )


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user_with_db_context),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required."
        )

    stmt = select(User).where(
        User.id == current_user.id, User.tenant_id == current_user.tenant_id
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    previous_persona = str(getattr(user, "persona", "")) or None
    user.persona = payload.persona.value

    audit = AuditLogger(db=db, tenant_id=current_user.tenant_id)
    await audit.log(
        event_type=AuditEventType.SETTINGS_UPDATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_ip=_client_ip(request),
        resource_type="user_profile",
        resource_id=str(current_user.id),
        details={
            "setting": "persona",
            "previous": previous_persona,
            "new": payload.persona.value,
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )

    await db.commit()

    logger.info(
        "user_persona_updated",
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id),
        previous=previous_persona,
        persona=payload.persona.value,
    )

    # Return the new persona immediately (tier/role come from auth context).
    return ProfileResponse(
        email=current_user.email,
        role=current_user.role,
        tier=current_user.tier,
        persona=payload.persona,
    )
