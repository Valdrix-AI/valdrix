"""
ActiveOps (Remediation) Settings API - Modular Split from settings.py

Handles autonomous remediation preferences per tenant.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import get_current_user, CurrentUser
from app.db.session import get_db
from app.models.settings import ActiveOpsSettings

logger = structlog.get_logger()
router = APIRouter(prefix="/activeops", tags=["Settings - ActiveOps"])


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
    min_confidence_threshold: float = Field(
        0.95, ge=0.5, le=1.0, 
        description="Minimum AI confidence for auto-remediation (0.5-1.0)"
    )


# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=ActiveOpsSettingsResponse)
async def get_activeops_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get ActiveOps (autonomous remediation) settings for the current tenant.
    
    Creates default settings if none exist.
    """
    result = await db.execute(
        select(ActiveOpsSettings).where(
            ActiveOpsSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = ActiveOpsSettings(
            tenant_id=current_user.tenant_id,
            auto_pilot_enabled=False,
            min_confidence_threshold=0.95,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return settings


@router.put("", response_model=ActiveOpsSettingsResponse)
async def update_activeops_settings(
    data: ActiveOpsSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update ActiveOps (autonomous remediation) settings for the current tenant.
    
    Warning: Enabling auto_pilot_enabled allows AI to execute remediations
    automatically when confidence exceeds the threshold.
    """
    result = await db.execute(
        select(ActiveOpsSettings).where(
            ActiveOpsSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = ActiveOpsSettings(tenant_id=current_user.tenant_id)
        db.add(settings)
    
    settings.auto_pilot_enabled = data.auto_pilot_enabled
    settings.min_confidence_threshold = data.min_confidence_threshold
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(
        "activeops_settings_updated",
        tenant_id=str(current_user.tenant_id),
        auto_pilot=settings.auto_pilot_enabled,
        confidence_threshold=settings.min_confidence_threshold
    )
    
    return settings
