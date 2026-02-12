"""
ActiveOps Settings API

Manages autonomous remediation (ActiveOps) settings for tenants.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
from app.shared.core.logging import audit_log
from app.shared.db.session import get_db
from app.models.remediation_settings import RemediationSettings

logger = structlog.get_logger()
router = APIRouter(tags=["ActiveOps"])


# ============================================================
# Pydantic Schemas
# ============================================================

class ActiveOpsSettingsResponse(BaseModel):
    """Response for ActiveOps (remediation) settings."""
    auto_pilot_enabled: bool
    min_confidence_threshold: float

    model_config = ConfigDict(from_attributes=True)


class ActiveOpsSettingsUpdate(BaseModel):
    """Request to update ActiveOps settings."""
    auto_pilot_enabled: bool = Field(False, description="Enable autonomous remediation")
    min_confidence_threshold: float = Field(0.95, ge=0.5, le=1.0, description="Minimum AI confidence (0.5-1.0)")


# ============================================================
# API Endpoints
# ============================================================

@router.get("/activeops", response_model=ActiveOpsSettingsResponse)
async def get_activeops_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActiveOpsSettingsResponse:
    """
    Get ActiveOps (Autonomous Remediation) settings for the current tenant.
    """
    result = await db.execute(
        select(RemediationSettings).where(
            RemediationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    # Create default settings if not exists
    if not settings:
        settings = RemediationSettings(
            tenant_id=current_user.tenant_id,
            auto_pilot_enabled=False,
            min_confidence_threshold=0.95,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info("activeops_settings_created", tenant_id=str(current_user.tenant_id))

    return ActiveOpsSettingsResponse.model_validate(settings)


@router.put("/activeops", response_model=ActiveOpsSettingsResponse)
async def update_activeops_settings(
    data: ActiveOpsSettingsUpdate,
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> ActiveOpsSettingsResponse:
    """
    Update ActiveOps settings for the current tenant.
    """
    result = await db.execute(
        select(RemediationSettings).where(
            RemediationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = RemediationSettings(
            tenant_id=current_user.tenant_id,
            **data.model_dump()
        )
        db.add(settings)
    else:
        updates = data.model_dump()
        settings.auto_pilot_enabled = updates["auto_pilot_enabled"]
        settings.min_confidence_threshold = updates["min_confidence_threshold"]

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "activeops_settings_updated",
        tenant_id=str(current_user.tenant_id),
        auto_pilot=settings.auto_pilot_enabled,
        threshold=float(settings.min_confidence_threshold)
    )

    audit_log(
        "settings.activeops_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        {"auto_pilot_enabled": settings.auto_pilot_enabled, "threshold": float(settings.min_confidence_threshold)}
    )

    return ActiveOpsSettingsResponse.model_validate(settings)
