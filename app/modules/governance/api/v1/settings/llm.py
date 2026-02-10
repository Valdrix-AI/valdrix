"""
LLM Settings API

Manages LLM provider preferences and budget settings for tenants.
Supports BYOK (Bring Your Own Key) for OpenAI, Claude, Google, and Groq.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
from app.shared.core.logging import audit_log
from app.shared.db.session import get_db
from app.models.llm import LLMBudget

logger = structlog.get_logger()
router = APIRouter(tags=["LLM"])


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

    # Optional API Key Overrides (BYOK)
    openai_api_key: str | None = Field(None, max_length=255)
    claude_api_key: str | None = Field(None, max_length=255)
    google_api_key: str | None = Field(None, max_length=255)
    groq_api_key: str | None = Field(None, max_length=255)


# ============================================================
# API Endpoints
# ============================================================

@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get LLM budget and selection settings for the current tenant.
    """
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
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update LLM budget and selection settings for the current tenant.
    """
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
        update_data = data.model_dump()
        # Item 15: Validate thresholds at boundaries
        if update_data["alert_threshold_percent"] == 0:
            logger.info("llm_alert_threshold_zero", tenant_id=str(current_user.tenant_id))
        elif update_data["alert_threshold_percent"] == 100:
            logger.info("llm_alert_threshold_max", tenant_id=str(current_user.tenant_id))

        allowed_fields = {
            "monthly_limit_usd",
            "alert_threshold_percent",
            "hard_limit",
            "preferred_provider",
            "preferred_model",
            "openai_api_key",
            "claude_api_key",
            "google_api_key",
            "groq_api_key",
        }

        for key in allowed_fields:
            if key in update_data:
                setattr(settings, key, update_data[key])

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "llm_settings_updated",
        tenant_id=str(current_user.tenant_id),
        provider=settings.preferred_provider,
        model=settings.preferred_model,
    )

    # SEC: Audit log critical settings change
    audit_log(
        "settings.llm_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        {
            "monthly_limit": float(settings.monthly_limit_usd),
            "provider": settings.preferred_provider,
            "model": settings.preferred_model,
            "keys_updated": [k for k, v in data.model_dump().items() if "api_key" in k and v is not None]
        }
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
    from app.shared.llm.pricing_data import LLM_PRICING

    result = {}
    for provider, models in LLM_PRICING.items():
        result[provider] = list(models.keys())

    return result
