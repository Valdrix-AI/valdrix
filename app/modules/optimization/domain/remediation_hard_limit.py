from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from app.models.remediation import RemediationAction, RemediationRequest, RemediationStatus
from app.shared.core.config import get_settings
from app.shared.core.constants import SYSTEM_USER_ID

logger = structlog.get_logger()


async def enforce_hard_limit_for_tenant(service: Any, tenant_id: UUID) -> list[UUID]:
    """
    Enforce hard limits for a tenant.
    """
    from app.shared.llm.budget_manager import BudgetStatus, LLMBudgetManager

    status = await LLMBudgetManager.check_budget(tenant_id, service.db)
    if status != BudgetStatus.HARD_LIMIT:
        return []

    logger.warning("enforcing_hard_limit_for_tenant", tenant_id=str(tenant_id))
    settings = get_settings()
    safe_actions = {
        RemediationAction.STOP_INSTANCE,
        RemediationAction.RESIZE_INSTANCE,
        RemediationAction.STOP_RDS_INSTANCE,
    }

    result = await service.db.execute(
        select(RemediationRequest)
        .where(RemediationRequest.tenant_id == tenant_id)
        .where(RemediationRequest.status == RemediationStatus.PENDING)
        .where(RemediationRequest.confidence_score >= Decimal("0.90"))
        .where(RemediationRequest.action.in_(safe_actions))
        .order_by(RemediationRequest.estimated_monthly_savings.desc())
    )
    requests = result.scalars().all()

    executed_ids: list[UUID] = []
    for req in requests:
        try:
            if req.action not in safe_actions:
                logger.warning(
                    "hard_limit_request_requires_manual_review",
                    request_id=str(req.id),
                    tenant_id=str(tenant_id),
                    action=req.action.value if req.action else None,
                )
                continue

            req.status = RemediationStatus.APPROVED
            req.reviewed_by_user_id = SYSTEM_USER_ID
            req.review_notes = "AUTO_APPROVED: Budget Hard Limit Exceeded"
            await service.db.commit()

            await service.execute(
                req.id,
                tenant_id,
                bypass_grace_period=settings.AUTOPILOT_BYPASS_GRACE_PERIOD,
            )
            executed_ids.append(req.id)
        except Exception as exc:
            logger.error(
                "hard_limit_enforcement_failed",
                request_id=str(req.id),
                error=str(exc),
            )

    return executed_ids
