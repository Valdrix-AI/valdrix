"""
Carbon Settings API

Manages carbon budget and sustainability settings for tenants.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.carbon_settings import CarbonSettings

logger = structlog.get_logger()
router = APIRouter(tags=["Carbon"])


# ============================================================
# Pydantic Schemas
# ============================================================

class CarbonSettingsResponse(BaseModel):
    """Response for carbon settings."""
    carbon_budget_kg: float
    alert_threshold_percent: int
    default_region: str
    email_enabled: bool
    email_recipients: str | None

    model_config = ConfigDict(from_attributes=True)


class CarbonSettingsUpdate(BaseModel):
    """Request to update carbon settings."""
    carbon_budget_kg: float = Field(100.0, ge=0, description="Monthly CO2 budget in kg")
    alert_threshold_percent: int = Field(80, ge=0, le=100, description="Warning threshold %")
    default_region: str = Field("us-east-1", description="Default AWS region for carbon intensity")
    email_enabled: bool = Field(False, description="Enable email notifications for carbon alerts")
    email_recipients: str | None = Field(None, description="Comma-separated email addresses")


# ============================================================
# API Endpoints
# ============================================================

@router.get("/carbon", response_model=CarbonSettingsResponse)
async def get_carbon_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get carbon budget settings for the current tenant.

    Creates default settings if none exist.
    """
    result = await db.execute(
        select(CarbonSettings).where(
            CarbonSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    # Create default settings if not exists
    if not settings:
        settings = CarbonSettings(
            tenant_id=current_user.tenant_id,
            carbon_budget_kg=100.0,
            alert_threshold_percent=80,
            default_region="us-east-1",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info(
            "carbon_settings_created",
            tenant_id=str(current_user.tenant_id),
        )

    return settings


@router.put("/carbon", response_model=CarbonSettingsResponse)
async def update_carbon_settings(
    data: CarbonSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update carbon budget settings for the current tenant.

    Creates settings if none exist.
    """
    result = await db.execute(
        select(CarbonSettings).where(
            CarbonSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    if not settings:
        # Create new settings
        settings = CarbonSettings(
            tenant_id=current_user.tenant_id,
            **data.model_dump()
        )
        db.add(settings)
    else:
        # Update existing settings
        for key, value in data.model_dump().items():
            setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "carbon_settings_updated",
        tenant_id=str(current_user.tenant_id),
        budget_kg=settings.carbon_budget_kg,
        threshold=settings.alert_threshold_percent,
    )

    return settings
