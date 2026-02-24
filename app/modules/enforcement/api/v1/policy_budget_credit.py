from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403
from app.modules.enforcement.api.v1.schemas import (
    BudgetResponse,
    BudgetUpsertRequest,
    CreditCreateRequest,
    CreditResponse,
    PolicyResponse,
    PolicyUpdateRequest,
)
from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


def _policy_to_response(policy: object) -> PolicyResponse:
    return PolicyResponse(
        terraform_mode=getattr(policy, "terraform_mode"),
        k8s_admission_mode=getattr(policy, "k8s_admission_mode"),
        require_approval_for_prod=bool(getattr(policy, "require_approval_for_prod")),
        require_approval_for_nonprod=bool(
            getattr(policy, "require_approval_for_nonprod")
        ),
        auto_approve_below_monthly_usd=getattr(policy, "auto_approve_below_monthly_usd"),
        hard_deny_above_monthly_usd=getattr(policy, "hard_deny_above_monthly_usd"),
        default_ttl_seconds=int(getattr(policy, "default_ttl_seconds")),
        policy_version=int(getattr(policy, "policy_version")),
        updated_at=getattr(policy, "updated_at"),
    )


@router.get("/policies", response_model=PolicyResponse)
async def get_policy(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    service = EnforcementService(db)
    policy = await service.get_or_create_policy(tenant_or_403(current_user))
    await db.commit()
    await db.refresh(policy)
    return _policy_to_response(policy)


@router.post("/policies", response_model=PolicyResponse)
async def upsert_policy(
    payload: PolicyUpdateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    service = EnforcementService(db)
    policy = await service.update_policy(
        tenant_id=tenant_or_403(current_user),
        terraform_mode=payload.terraform_mode,
        k8s_admission_mode=payload.k8s_admission_mode,
        require_approval_for_prod=payload.require_approval_for_prod,
        require_approval_for_nonprod=payload.require_approval_for_nonprod,
        auto_approve_below_monthly_usd=payload.auto_approve_below_monthly_usd,
        hard_deny_above_monthly_usd=payload.hard_deny_above_monthly_usd,
        default_ttl_seconds=payload.default_ttl_seconds,
    )
    return _policy_to_response(policy)


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetResponse]:
    service = EnforcementService(db)
    budgets = await service.list_budgets(tenant_or_403(current_user))
    return [
        BudgetResponse(
            id=item.id,
            scope_key=item.scope_key,
            monthly_limit_usd=item.monthly_limit_usd,
            active=bool(item.active),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in budgets
    ]


@router.post("/budgets", response_model=BudgetResponse)
async def upsert_budget(
    payload: BudgetUpsertRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    service = EnforcementService(db)
    budget = await service.upsert_budget(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        scope_key=payload.scope_key,
        monthly_limit_usd=payload.monthly_limit_usd,
        active=payload.active,
    )
    return BudgetResponse(
        id=budget.id,
        scope_key=budget.scope_key,
        monthly_limit_usd=budget.monthly_limit_usd,
        active=bool(budget.active),
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@router.get("/credits", response_model=list[CreditResponse])
async def list_credits(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[CreditResponse]:
    service = EnforcementService(db)
    credits = await service.list_credits(tenant_or_403(current_user))
    return [
        CreditResponse(
            id=item.id,
            scope_key=item.scope_key,
            total_amount_usd=item.total_amount_usd,
            remaining_amount_usd=item.remaining_amount_usd,
            expires_at=item.expires_at,
            reason=item.reason,
            active=bool(item.active),
            created_at=item.created_at,
        )
        for item in credits
    ]


@router.post("/credits", response_model=CreditResponse)
async def create_credit(
    payload: CreditCreateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> CreditResponse:
    service = EnforcementService(db)
    credit = await service.create_credit_grant(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        scope_key=payload.scope_key,
        total_amount_usd=payload.total_amount_usd,
        expires_at=payload.expires_at,
        reason=payload.reason,
    )
    return CreditResponse(
        id=credit.id,
        scope_key=credit.scope_key,
        total_amount_usd=credit.total_amount_usd,
        remaining_amount_usd=credit.remaining_amount_usd,
        expires_at=credit.expires_at,
        reason=credit.reason,
        active=bool(credit.active),
        created_at=credit.created_at,
    )
