"""
Carbon Settings API

Manages carbon budget and sustainability settings for tenants.
"""

from fastapi import APIRouter, Depends
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    field_validator,
    model_validator,
    EmailStr,
    TypeAdapter,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
from app.shared.core.logging import audit_log
from app.shared.db.session import get_db
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
    alert_threshold_percent: int = Field(
        80, ge=0, le=100, description="Warning threshold %"
    )
    default_region: str = Field(
        "us-east-1", description="Default AWS region for carbon intensity"
    )
    email_enabled: bool = Field(
        False, description="Enable email notifications for carbon alerts"
    )
    email_recipients: str | None = Field(
        None, description="Comma-separated email addresses"
    )

    @field_validator("email_recipients")
    @classmethod
    def _validate_email_recipients(cls, value: str | None) -> str | None:
        if value is None:
            return None
        emails = [e.strip() for e in value.split(",") if e.strip()]
        if not emails:
            return None
        adapter = TypeAdapter(EmailStr)
        for email in emails:
            adapter.validate_python(email)
        return ", ".join(emails)

    @model_validator(mode="after")
    def _validate_email_settings(self) -> "CarbonSettingsUpdate":
        if self.email_enabled and not self.email_recipients:
            raise ValueError("email_recipients is required when email_enabled is true")
        return self

    @field_validator("email_recipients")
    @classmethod
    def _validate_email_recipients(cls, value: str | None) -> str | None:
        if value is None:
            return None
        emails = [e.strip() for e in value.split(",") if e.strip()]
        if not emails:
            return None
        adapter = TypeAdapter(EmailStr)
        for email in emails:
            adapter.validate_python(email)
        return ", ".join(emails)

    @model_validator(mode="after")
    def _validate_email_settings(self):
        if self.email_enabled and not self.email_recipients:
            raise ValueError("email_recipients is required when email_enabled is true")
        return self


# ============================================================
# API Endpoints
# ============================================================


@router.get("/carbon", response_model=CarbonSettingsResponse)
async def get_carbon_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CarbonSettingsResponse:
    """
    Get carbon budget settings for the current tenant.

    Creates default settings if none exist.
    """
    result = await db.execute(
        select(CarbonSettings).where(CarbonSettings.tenant_id == current_user.tenant_id)
    )
    settings = result.scalar_one_or_none()

    # Create default settings if not exists
    if not settings:
        settings = CarbonSettings(
            tenant_id=current_user.tenant_id,
            carbon_budget_kg=100.0,
            alert_threshold_percent=80,
            default_region="us-east-1",
            email_enabled=False,
            email_recipients=None,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info(
            "carbon_settings_created",
            tenant_id=str(current_user.tenant_id),
        )

    return CarbonSettingsResponse(
        carbon_budget_kg=float(settings.carbon_budget_kg),
        alert_threshold_percent=settings.alert_threshold_percent,
        default_region=settings.default_region,
        email_enabled=bool(settings.email_enabled),
        email_recipients=settings.email_recipients,
    )


@router.put("/carbon", response_model=CarbonSettingsResponse)
async def update_carbon_settings(
    data: CarbonSettingsUpdate,
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> CarbonSettingsResponse:
    """
    Update carbon budget settings for the current tenant.

    Creates settings if none exist.
    """
    result = await db.execute(
        select(CarbonSettings).where(CarbonSettings.tenant_id == current_user.tenant_id)
    )
    settings = result.scalar_one_or_none()

    if not settings:
        # Create new settings
        settings = CarbonSettings(tenant_id=current_user.tenant_id, **data.model_dump())
        db.add(settings)
    else:
        updates = data.model_dump()
        settings.carbon_budget_kg = updates["carbon_budget_kg"]
        settings.alert_threshold_percent = updates["alert_threshold_percent"]
        settings.default_region = updates["default_region"]
        settings.email_enabled = updates["email_enabled"]
        settings.email_recipients = updates["email_recipients"]

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "carbon_settings_updated",
        tenant_id=str(current_user.tenant_id),
        budget_kg=settings.carbon_budget_kg,
        threshold=settings.alert_threshold_percent,
    )

    audit_log(
        "settings.carbon_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        {
            "budget_kg": float(settings.carbon_budget_kg),
            "region": settings.default_region,
        },
    )

    return CarbonSettingsResponse(
        carbon_budget_kg=float(settings.carbon_budget_kg),
        alert_threshold_percent=settings.alert_threshold_percent,
        default_region=settings.default_region,
        email_enabled=bool(settings.email_enabled),
        email_recipients=settings.email_recipients,
    )
