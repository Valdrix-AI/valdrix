"""
LLM Settings API - Modular Split from settings.py

Handles LLM provider preferences and budget settings per tenant.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import get_current_user, CurrentUser
from app.db.session import get_db
from app.models.settings import LLMSettings
from app.core.security import encrypt_api_key

logger = structlog.get_logger()
router = APIRouter(prefix="/llm", tags=["Settings - LLM"])


# ============================================================
# Pydantic Schemas
# ============================================================

class LLMSettingsResponse(BaseModel):
    """Response for LLM budget and selection settings."""
    monthly_limit_usd: float
    alert_threshold_percent: int
    hard_limit: bool
    preferred_provider: str
    preferred_model: str
    has_openai_key: bool = False
    has_claude_key: bool = False
    has_google_key: bool = False
    has_groq_key: bool = False
    model_config = ConfigDict(from_attributes=True)


class LLMSettingsUpdate(BaseModel):
    """Request to update LLM settings."""
    monthly_limit_usd: float = Field(10.0, ge=0, description="Monthly USD budget")
    alert_threshold_percent: int = Field(80, ge=0, le=100, description="Alert threshold %")
    hard_limit: bool = Field(False, description="Stop processing at limit")
    preferred_provider: str = Field("groq", description="openai, claude, google, groq")
    preferred_model: str = Field("", description="Specific model name")
    openai_api_key: str | None = Field(None, max_length=255)
    claude_api_key: str | None = Field(None, max_length=255)
    google_api_key: str | None = Field(None, max_length=255)
    groq_api_key: str | None = Field(None, max_length=255)


# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get LLM provider and budget settings for the current tenant.
    
    Creates default settings if none exist.
    """
    result = await db.execute(
        select(LLMSettings).where(
            LLMSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = LLMSettings(
            tenant_id=current_user.tenant_id,
            monthly_limit_usd=10.0,
            alert_threshold_percent=80,
            hard_limit=False,
            preferred_provider="groq",
            preferred_model="",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    # Build response with key presence flags
    response = LLMSettingsResponse(
        monthly_limit_usd=settings.monthly_limit_usd,
        alert_threshold_percent=settings.alert_threshold_percent,
        hard_limit=settings.hard_limit,
        preferred_provider=settings.preferred_provider,
        preferred_model=settings.preferred_model or "",
        has_openai_key=bool(settings.openai_api_key_encrypted),
        has_claude_key=bool(settings.claude_api_key_encrypted),
        has_google_key=bool(settings.google_api_key_encrypted),
        has_groq_key=bool(settings.groq_api_key_encrypted),
    )
    
    return response


@router.put("", response_model=LLMSettingsResponse)
async def update_llm_settings(
    data: LLMSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update LLM provider and budget settings for the current tenant.
    
    API keys are encrypted before storage (BYOK - Bring Your Own Key).
    """
    result = await db.execute(
        select(LLMSettings).where(
            LLMSettings.tenant_id == current_user.tenant_id
        )
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = LLMSettings(tenant_id=current_user.tenant_id)
        db.add(settings)
    
    # Update non-key fields
    settings.monthly_limit_usd = data.monthly_limit_usd
    settings.alert_threshold_percent = data.alert_threshold_percent
    settings.hard_limit = data.hard_limit
    settings.preferred_provider = data.preferred_provider
    settings.preferred_model = data.preferred_model or ""
    
    # Encrypt and store API keys if provided
    if data.openai_api_key:
        settings.openai_api_key_encrypted = encrypt_api_key(data.openai_api_key)
    if data.claude_api_key:
        settings.claude_api_key_encrypted = encrypt_api_key(data.claude_api_key)
    if data.google_api_key:
        settings.google_api_key_encrypted = encrypt_api_key(data.google_api_key)
    if data.groq_api_key:
        settings.groq_api_key_encrypted = encrypt_api_key(data.groq_api_key)
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(
        "llm_settings_updated",
        tenant_id=str(current_user.tenant_id),
        provider=settings.preferred_provider,
        limit_usd=settings.monthly_limit_usd
    )
    
    return LLMSettingsResponse(
        monthly_limit_usd=settings.monthly_limit_usd,
        alert_threshold_percent=settings.alert_threshold_percent,
        hard_limit=settings.hard_limit,
        preferred_provider=settings.preferred_provider,
        preferred_model=settings.preferred_model or "",
        has_openai_key=bool(settings.openai_api_key_encrypted),
        has_claude_key=bool(settings.claude_api_key_encrypted),
        has_google_key=bool(settings.google_api_key_encrypted),
        has_groq_key=bool(settings.groq_api_key_encrypted),
    )
