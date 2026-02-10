"""
Notification Settings API

Manages Slack and alert notification preferences for tenants.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
from app.shared.core.logging import audit_log
from app.shared.db.session import get_db
from app.models.notification_settings import NotificationSettings

logger = structlog.get_logger()
router = APIRouter(tags=["Notifications"])


# ============================================================
# Pydantic Schemas
# ============================================================

class NotificationSettingsResponse(BaseModel):
    """Response for notification settings."""
    slack_enabled: bool
    slack_channel_override: str | None
    digest_schedule: str  # "daily", "weekly", "disabled"
    digest_hour: int  # 0-23
    digest_minute: int  # 0-59
    alert_on_budget_warning: bool
    alert_on_budget_exceeded: bool
    alert_on_zombie_detected: bool

    model_config = ConfigDict(from_attributes=True)


class NotificationSettingsUpdate(BaseModel):
    """Request to update notification settings."""
    slack_enabled: bool = Field(True, description="Enable/disable Slack notifications")
    slack_channel_override: str | None = Field(None, max_length=64, pattern=r"^(#[\w-]+|[CU][A-Z0-9]+)?$", description="Override Slack channel ID (e.g., #general or C0123456789)")
    digest_schedule: str = Field("daily", pattern="^(daily|weekly|disabled)$", description="Digest frequency")
    digest_hour: int = Field(9, ge=0, le=23, description="Hour to send digest (UTC)")
    digest_minute: int = Field(0, ge=0, le=59, description="Minute to send digest")
    alert_on_budget_warning: bool = Field(True, description="Alert when approaching budget")
    alert_on_budget_exceeded: bool = Field(True, description="Alert when budget exceeded")
    alert_on_zombie_detected: bool = Field(True, description="Alert on zombie resources")


# ============================================================
# API Endpoints
# ============================================================

@router.get("/notifications", response_model=NotificationSettingsResponse)
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

    # Create default settings if not exists
    if not settings:
        settings = NotificationSettings(
            tenant_id=current_user.tenant_id,
            slack_enabled=True,
            digest_schedule="daily",
            digest_hour=9,
            digest_minute=0,
            alert_on_budget_warning=True,
            alert_on_budget_exceeded=True,
            alert_on_zombie_detected=True,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info(
            "notification_settings_created",
            tenant_id=str(current_user.tenant_id),
        )

    return settings


@router.put("/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: CurrentUser = Depends(requires_role("admin")),
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
        # Create new settings
        settings = NotificationSettings(
            tenant_id=current_user.tenant_id,
            **data.model_dump()
        )
        db.add(settings)
    else:
        updates = data.model_dump()
        settings.slack_enabled = updates["slack_enabled"]
        settings.slack_channel_override = updates["slack_channel_override"]
        settings.digest_schedule = updates["digest_schedule"]
        settings.digest_hour = updates["digest_hour"]
        settings.digest_minute = updates["digest_minute"]
        settings.alert_on_budget_warning = updates["alert_on_budget_warning"]
        settings.alert_on_budget_exceeded = updates["alert_on_budget_exceeded"]
        settings.alert_on_zombie_detected = updates["alert_on_zombie_detected"]

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "notification_settings_updated",
        tenant_id=str(current_user.tenant_id),
        digest_schedule=settings.digest_schedule,
    )

    audit_log(
        "settings.notifications_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        {
            "slack_enabled": settings.slack_enabled,
            "digest": settings.digest_schedule,
            "slack_override": bool(settings.slack_channel_override)
        }
    )

    return settings


@router.post("/notifications/test-slack")
async def test_slack_notification(
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a test notification to Slack.

    Uses the configured Slack channel or override.
    """
    from app.shared.core.config import get_settings
    from app.modules.notifications.domain import SlackService

    settings = get_settings()

    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_CHANNEL_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack is not configured. Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID in environment."
        )

    # Item: Honor channel override defined in settings
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == current_user.tenant_id
        )
    )
    db_settings = result.scalar_one_or_none()
    target_channel = (db_settings.slack_channel_override if db_settings else None) or settings.SLACK_CHANNEL_ID

    try:
        slack = SlackService(settings.SLACK_BOT_TOKEN, target_channel)
        success = await slack.send_alert(
            title="Test Notification",
            message=f"This is a test alert from Valdrix.\n\nUser: {current_user.email}",
            severity="info"
        )

        if success:
            return {"status": "success", "message": "Test notification sent to Slack"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send Slack notification"
            )
    except Exception as e:
        logger.error("slack_test_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slack test failed: {str(e)}"
        ) from e
