"""
Notification Settings API - Modular Split from settings.py

Handles Slack notification preferences per tenant.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import get_current_user, CurrentUser
from app.db.session import get_db
from app.models.settings import NotificationSettings
from app.services.notifications.slack import SlackNotifier

logger = structlog.get_logger()
router = APIRouter(prefix="/settings/notifications", tags=["Settings - Notifications"])


# ============================================================
# Pydantic Schemas
# ============================================================

class NotificationSettingsResponse(BaseModel):
    """Response for notification settings."""
    slack_enabled: bool
    slack_channel_override: str | None
    digest_schedule: str
    digest_hour: int
    digest_minute: int
    alert_on_budget_warning: bool
    alert_on_budget_exceeded: bool
    alert_on_zombie_detected: bool
    model_config = ConfigDict(from_attributes=True)


class NotificationSettingsUpdate(BaseModel):
    """Request to update notification settings."""
    slack_enabled: bool = Field(True, description="Enable/disable Slack notifications")
    slack_channel_override: str | None = Field(None, description="Override default Slack channel")
    digest_schedule: str = Field("weekly", description="daily, weekly, or monthly")
    digest_hour: int = Field(9, ge=0, le=23, description="Hour to send digest (0-23)")
    digest_minute: int = Field(0, ge=0, le=59, description="Minute to send digest (0-59)")
    alert_on_budget_warning: bool = Field(True, description="Alert on budget warning (80%)")
    alert_on_budget_exceeded: bool = Field(True, description="Alert when budget exceeded")
    alert_on_zombie_detected: bool = Field(True, description="Alert on zombie resources")


# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get notification settings for the current tenant.
    
    Creates default settings if none exist.
    """
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Create default settings
        settings = NotificationSettings(
            tenant_id=current_user.tenant_id,
            slack_enabled=True,
            digest_schedule="weekly",
            digest_hour=9,
            digest_minute=0,
            alert_on_budget_warning=True,
            alert_on_budget_exceeded=True,
            alert_on_zombie_detected=True,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return settings


@router.put("", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update notification settings for the current tenant.
    
    Creates settings if none exist.
    """
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = NotificationSettings(tenant_id=current_user.tenant_id)
        db.add(settings)
    
    # Update fields
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(
        "notification_settings_updated",
        tenant_id=str(current_user.tenant_id),
        slack_enabled=settings.slack_enabled
    )
    
    return settings


@router.post("/test", status_code=status.HTTP_200_OK)
async def test_slack_notification(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Send a test notification to Slack.
    
    Uses the configured Slack channel or override.
    """
    notifier = SlackNotifier()
    
    if not notifier.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack is not configured. Set SLACK_WEBHOOK_URL environment variable."
        )
    
    success = await notifier.send_test_notification()
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test notification. Check Slack webhook configuration."
        )
    
    return {"message": "Test notification sent successfully"}
