"""
ActiveOps Settings API

Manages autonomous remediation (ActiveOps) settings for tenants.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser, get_current_user, requires_role
from app.shared.core.logging import audit_log
from app.shared.db.session import get_db
from app.models.remediation_settings import RemediationSettings
from app.shared.remediation.hard_cap_service import BudgetHardCapService

logger = structlog.get_logger()
router = APIRouter(tags=["ActiveOps"])


# ============================================================
# Pydantic Schemas
# ============================================================


class ActiveOpsSettingsResponse(BaseModel):
    """Response for ActiveOps (remediation) settings."""

    auto_pilot_enabled: bool
    min_confidence_threshold: float
    policy_enabled: bool
    policy_block_production_destructive: bool
    policy_require_gpu_override: bool
    policy_low_confidence_warn_threshold: float
    policy_violation_notify_slack: bool
    policy_violation_notify_jira: bool
    policy_escalation_required_role: str

    model_config = ConfigDict(from_attributes=True)


class ActiveOpsSettingsUpdate(BaseModel):
    """Request to update ActiveOps settings."""

    auto_pilot_enabled: bool = Field(False, description="Enable autonomous remediation")
    min_confidence_threshold: float = Field(
        0.95, ge=0.5, le=1.0, description="Minimum AI confidence (0.5-1.0)"
    )
    policy_enabled: bool = Field(
        True, description="Enable request-level policy guardrails"
    )
    policy_block_production_destructive: bool = Field(
        True, description="Block destructive actions on production-like resources"
    )
    policy_require_gpu_override: bool = Field(
        True,
        description="Escalate GPU-impacting remediations unless explicit override exists",
    )
    policy_low_confidence_warn_threshold: float = Field(
        0.90,
        ge=0.5,
        le=1.0,
        description="Warn when confidence score is below this threshold",
    )
    policy_violation_notify_slack: bool = Field(
        True, description="Send policy violations to Slack"
    )
    policy_violation_notify_jira: bool = Field(
        False, description="Send policy violations to Jira"
    )
    policy_escalation_required_role: str = Field(
        "owner",
        pattern="^(owner|admin)$",
        description="Role required to approve escalated remediation",
    )


class HardCapReactivationRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Operator rationale for reactivating tenant connectors after hard-cap enforcement.",
    )


class HardCapReactivationResponse(BaseModel):
    status: str
    restored_connections: int


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
            policy_enabled=True,
            policy_block_production_destructive=True,
            policy_require_gpu_override=True,
            policy_low_confidence_warn_threshold=0.90,
            policy_violation_notify_slack=True,
            policy_violation_notify_jira=False,
            policy_escalation_required_role="owner",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

        logger.info("activeops_settings_created", tenant_id=str(current_user.tenant_id))

    return ActiveOpsSettingsResponse.model_validate(settings)


@router.post(
    "/activeops/hard-cap/reactivate",
    response_model=HardCapReactivationResponse,
)
async def reactivate_hard_cap(
    data: HardCapReactivationRequest,
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> HardCapReactivationResponse:
    """
    Restore connection activity after a hard-cap enforcement event.
    """
    service = BudgetHardCapService(db)
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    try:
        restored_connections = await service.reverse_hard_cap(
            tenant_id,
            actor_id=current_user.id,
            reason=data.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "activeops_hard_cap_reactivated",
        tenant_id=str(current_user.tenant_id),
        actor_id=str(current_user.id),
        restored_connections=restored_connections,
    )

    return HardCapReactivationResponse(
        status="reactivated",
        restored_connections=restored_connections,
    )


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
            tenant_id=current_user.tenant_id, **data.model_dump()
        )
        db.add(settings)
    else:
        updates = data.model_dump()
        settings.auto_pilot_enabled = updates["auto_pilot_enabled"]
        settings.min_confidence_threshold = updates["min_confidence_threshold"]
        settings.policy_enabled = updates["policy_enabled"]
        settings.policy_block_production_destructive = updates[
            "policy_block_production_destructive"
        ]
        settings.policy_require_gpu_override = updates["policy_require_gpu_override"]
        settings.policy_low_confidence_warn_threshold = updates[
            "policy_low_confidence_warn_threshold"
        ]
        settings.policy_violation_notify_slack = updates[
            "policy_violation_notify_slack"
        ]
        settings.policy_violation_notify_jira = updates["policy_violation_notify_jira"]
        settings.policy_escalation_required_role = updates[
            "policy_escalation_required_role"
        ]

    await db.commit()
    await db.refresh(settings)

    logger.info(
        "activeops_settings_updated",
        tenant_id=str(current_user.tenant_id),
        auto_pilot=settings.auto_pilot_enabled,
        threshold=float(settings.min_confidence_threshold),
        policy_enabled=settings.policy_enabled,
    )

    audit_log(
        "settings.activeops_updated",
        str(current_user.id),
        str(current_user.tenant_id),
        {
            "auto_pilot_enabled": settings.auto_pilot_enabled,
            "threshold": float(settings.min_confidence_threshold),
            "policy_enabled": settings.policy_enabled,
            "policy_block_production_destructive": settings.policy_block_production_destructive,
            "policy_require_gpu_override": settings.policy_require_gpu_override,
            "policy_low_confidence_warn_threshold": float(
                settings.policy_low_confidence_warn_threshold
            ),
            "policy_violation_notify_slack": settings.policy_violation_notify_slack,
            "policy_violation_notify_jira": settings.policy_violation_notify_jira,
            "policy_escalation_required_role": settings.policy_escalation_required_role,
        },
    )

    return ActiveOpsSettingsResponse.model_validate(settings)
