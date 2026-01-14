"""
Settings API Endpoints for Valdrix.
Manages per-tenant notification preferences.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings

logger = structlog.get_logger()
router = APIRouter(prefix="/settings", tags=["Settings"])


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
    slack_channel_override: str | None = Field(None, max_length=64, description="Override Slack channel ID")
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
        # Create new settings
        settings = NotificationSettings(
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
        "notification_settings_updated",
        tenant_id=str(current_user.tenant_id),
        digest_schedule=settings.digest_schedule,
    )

    return settings


@router.post("/notifications/test-slack")
async def test_slack_notification(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Send a test notification to Slack.

    Uses the configured Slack channel or override.
    """
    from app.core.config import get_settings
    from app.services.notifications import SlackService

    settings = get_settings()

    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_CHANNEL_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack is not configured. Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID in environment."
        )

    try:
        slack = SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)
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
        )


# ============================================================
# Carbon Settings Schemas
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
# LLM Settings Schemas
# ============================================================

class LLMSettingsResponse(BaseModel):
    """Response for LLM budget and selection settings."""
    monthly_limit_usd: float
    alert_threshold_percent: int
    hard_limit: bool
    preferred_provider: str
    preferred_model: str

    # API Key status (True if key is set, but don't return the actual key for security)
    has_openai_key: bool = False
    has_claude_key: bool = False
    has_google_key: bool = False
    has_groq_key: bool = False

    model_config = ConfigDict(from_attributes=True)


class LLMSettingsUpdate(BaseModel):
    """Request to update LLM settings."""
    monthly_limit_usd: float = Field(10.0, ge=0, description="Monthly USD budget for AI")
    alert_threshold_percent: int = Field(80, ge=0, le=100, description="Warning threshold %")
    hard_limit: bool = Field(False, description="Block requests if budget exceeded")
    preferred_provider: str = Field("groq", pattern="^(openai|claude|google|groq)$")
    preferred_model: str = Field("llama-3.3-70b-versatile")

    # Optional API Key Overrides
    openai_api_key: str | None = Field(None, max_length=255)
    claude_api_key: str | None = Field(None, max_length=255)
    google_api_key: str | None = Field(None, max_length=255)
    groq_api_key: str | None = Field(None, max_length=255)


# ============================================================
# ActiveOps (Remediation) Settings Schemas
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
# Carbon Settings Endpoints
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
    from app.models.carbon_settings import CarbonSettings

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
    from app.models.carbon_settings import CarbonSettings

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


# ============================================================
# LLM Settings Endpoints
# ============================================================

@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get LLM budget and selection settings for the current tenant.
    """
    from app.models.llm import LLMBudget

    result = await db.execute(
        select(LLMBudget).where(
            LLMBudget.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    # Create default budget if not exists
    if not settings:
        settings = LLMBudget(
            tenant_id=current_user.tenant_id,
            monthly_limit_usd=10.0,
            alert_threshold_percent=80,
            preferred_provider="groq",
            preferred_model="llama-3.3-70b-versatile",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info(
            "llm_settings_created",
            tenant_id=str(current_user.tenant_id),
        )

    # Map model flags for response
    return {
        "monthly_limit_usd": float(settings.monthly_limit_usd),
        "alert_threshold_percent": settings.alert_threshold_percent,
        "hard_limit": settings.hard_limit,
        "preferred_provider": settings.preferred_provider,
        "preferred_model": settings.preferred_model,
        "has_openai_key": bool(settings.openai_api_key),
        "has_claude_key": bool(settings.claude_api_key),
        "has_google_key": bool(settings.google_api_key),
        "has_groq_key": bool(settings.groq_api_key),
    }


@router.put("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(
    data: LLMSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update LLM budget and selection settings for the current tenant.
    """
    from app.models.llm import LLMBudget

    result = await db.execute(
        select(LLMBudget).where(
            LLMBudget.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()

    if not settings:
        settings = LLMBudget(
            tenant_id=current_user.tenant_id,
            **data.model_dump()
        )
        db.add(settings)
    else:
        for key, value in data.model_dump().items():
            setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "llm_settings_updated",
        tenant_id=str(current_user.tenant_id),
        provider=settings.preferred_provider,
        model=settings.preferred_model,
    )

    # Map model flags for response
    return {
        "monthly_limit_usd": float(settings.monthly_limit_usd),
        "alert_threshold_percent": settings.alert_threshold_percent,
        "hard_limit": settings.hard_limit,
        "preferred_provider": settings.preferred_provider,
        "preferred_model": settings.preferred_model,
        "has_openai_key": bool(settings.openai_api_key),
        "has_claude_key": bool(settings.claude_api_key),
        "has_google_key": bool(settings.google_api_key),
        "has_groq_key": bool(settings.groq_api_key),
    }


@router.get("/llm/models")
async def get_llm_models():
    """Returns available LLM providers and models."""
    from app.services.llm.usage_tracker import LLM_PRICING

    result = {}
    for provider, models in LLM_PRICING.items():
        result[provider] = list(models.keys())

    return result


# ============================================================
# ActiveOps Settings Endpoints
# ============================================================

@router.get("/activeops", response_model=ActiveOpsSettingsResponse)
async def get_activeops_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    return settings


@router.put("/activeops", response_model=ActiveOpsSettingsResponse)
async def update_activeops_settings(
    data: ActiveOpsSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
        for key, value in data.model_dump().items():
            setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "activeops_settings_updated",
        tenant_id=str(current_user.tenant_id),
        auto_pilot=settings.auto_pilot_enabled,
        threshold=float(settings.min_confidence_threshold)
    )

    return settings


# ============================================================
# Safety Status Endpoint (Circuit Breaker)
# ============================================================

class SafetyStatusResponse(BaseModel):
    """Response for safety/circuit breaker status."""
    circuit_state: str  # "closed", "open", "half_open"
    failure_count: int
    daily_savings_used: float
    daily_savings_limit: float
    last_failure_at: str | None
    can_execute: bool


@router.get("/safety", response_model=SafetyStatusResponse)
async def get_safety_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get circuit breaker and safety status for the current tenant.
    
    Shows:
    - Circuit state (closed=ok, open=blocked, half_open=testing)
    - Daily savings budget usage
    - Whether remediations can execute
    """
    from app.services.remediation.circuit_breaker import get_circuit_breaker
    from app.core.config import get_settings
    
    settings = get_settings()
    
    try:
        circuit_breaker = await get_circuit_breaker(str(current_user.tenant_id))
        
        state = await circuit_breaker.state.get("state", "closed")
        failure_count = await circuit_breaker.state.get("failure_count", 0)
        daily_savings = await circuit_breaker.state.get("daily_savings", 0.0)
        last_failure = await circuit_breaker.state.get("last_failure_at", None)
        
        can_execute = await circuit_breaker.can_execute()
        
        return SafetyStatusResponse(
            circuit_state=state,
            failure_count=failure_count,
            daily_savings_used=daily_savings,
            daily_savings_limit=settings.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS,
            last_failure_at=last_failure,
            can_execute=can_execute
        )
    except Exception as e:
        logger.error("safety_status_failed", error=str(e))
        # Return safe defaults
        return SafetyStatusResponse(
            circuit_state="unknown",
            failure_count=0,
            daily_savings_used=0.0,
            daily_savings_limit=settings.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS,
            last_failure_at=None,
            can_execute=True
        )


@router.post("/safety/reset")
async def reset_circuit_breaker(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually reset circuit breaker to closed state (admin-only).
    
    Use with caution - this allows remediations to proceed.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    from app.services.remediation.circuit_breaker import get_circuit_breaker
    
    try:
        circuit_breaker = await get_circuit_breaker(str(current_user.tenant_id))
        await circuit_breaker.reset()
        
        logger.info(
            "circuit_breaker_reset",
            tenant_id=str(current_user.tenant_id),
            by_user=str(current_user.id)
        )
        
        return {"status": "reset", "message": "Circuit breaker reset to closed state"}
    except Exception as e:
        logger.error("circuit_breaker_reset_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset circuit breaker"
        )
