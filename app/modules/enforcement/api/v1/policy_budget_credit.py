from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403, require_feature_or_403
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
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


def _policy_to_response(policy: object) -> PolicyResponse:
    return PolicyResponse(
        terraform_mode=getattr(policy, "terraform_mode"),
        terraform_mode_prod=getattr(policy, "terraform_mode_prod"),
        terraform_mode_nonprod=getattr(policy, "terraform_mode_nonprod"),
        k8s_admission_mode=getattr(policy, "k8s_admission_mode"),
        k8s_admission_mode_prod=getattr(policy, "k8s_admission_mode_prod"),
        k8s_admission_mode_nonprod=getattr(policy, "k8s_admission_mode_nonprod"),
        require_approval_for_prod=bool(getattr(policy, "require_approval_for_prod")),
        require_approval_for_nonprod=bool(
            getattr(policy, "require_approval_for_nonprod")
        ),
        enforce_prod_requester_reviewer_separation=bool(
            getattr(policy, "enforce_prod_requester_reviewer_separation", True)
        ),
        enforce_nonprod_requester_reviewer_separation=bool(
            getattr(policy, "enforce_nonprod_requester_reviewer_separation", False)
        ),
        plan_monthly_ceiling_usd=getattr(policy, "plan_monthly_ceiling_usd", None),
        enterprise_monthly_ceiling_usd=getattr(
            policy,
            "enterprise_monthly_ceiling_usd",
            None,
        ),
        auto_approve_below_monthly_usd=getattr(policy, "auto_approve_below_monthly_usd"),
        hard_deny_above_monthly_usd=getattr(policy, "hard_deny_above_monthly_usd"),
        default_ttl_seconds=int(getattr(policy, "default_ttl_seconds")),
        approval_routing_rules=list(getattr(policy, "approval_routing_rules", []) or []),
        policy_document_schema_version=getattr(
            policy,
            "policy_document_schema_version",
        ),
        policy_document_sha256=getattr(policy, "policy_document_sha256"),
        policy_document=getattr(policy, "policy_document"),
        policy_version=int(getattr(policy, "policy_version")),
        updated_at=getattr(policy, "updated_at"),
    )


@router.get("/policies", response_model=PolicyResponse)
async def get_policy(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementService(db)
    policy = await service.get_or_create_policy(tenant_or_403(current_user))
    await db.commit()
    return _policy_to_response(policy)


@router.post("/policies", response_model=PolicyResponse)
async def upsert_policy(
    payload: PolicyUpdateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementService(db)
    policy = await service.update_policy(
        tenant_id=tenant_or_403(current_user),
        terraform_mode=payload.terraform_mode,
        terraform_mode_prod=payload.terraform_mode_prod,
        terraform_mode_nonprod=payload.terraform_mode_nonprod,
        k8s_admission_mode=payload.k8s_admission_mode,
        k8s_admission_mode_prod=payload.k8s_admission_mode_prod,
        k8s_admission_mode_nonprod=payload.k8s_admission_mode_nonprod,
        require_approval_for_prod=payload.require_approval_for_prod,
        require_approval_for_nonprod=payload.require_approval_for_nonprod,
        enforce_prod_requester_reviewer_separation=payload.enforce_prod_requester_reviewer_separation,
        enforce_nonprod_requester_reviewer_separation=payload.enforce_nonprod_requester_reviewer_separation,
        plan_monthly_ceiling_usd=payload.plan_monthly_ceiling_usd,
        enterprise_monthly_ceiling_usd=payload.enterprise_monthly_ceiling_usd,
        auto_approve_below_monthly_usd=payload.auto_approve_below_monthly_usd,
        hard_deny_above_monthly_usd=payload.hard_deny_above_monthly_usd,
        default_ttl_seconds=payload.default_ttl_seconds,
        approval_routing_rules=[item.model_dump() for item in payload.approval_routing_rules],
        policy_document=(
            payload.policy_document.model_dump(mode="json")
            if payload.policy_document is not None
            else None
        ),
    )
    return _policy_to_response(policy)


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetResponse]:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
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
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
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
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementService(db)
    credits = await service.list_credits(tenant_or_403(current_user))
    return [
        CreditResponse(
            id=item.id,
            pool_type=item.pool_type,
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
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementService(db)
    credit = await service.create_credit_grant(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        pool_type=payload.pool_type,
        scope_key=payload.scope_key,
        total_amount_usd=payload.total_amount_usd,
        expires_at=payload.expires_at,
        reason=payload.reason,
    )
    return CreditResponse(
        id=credit.id,
        pool_type=credit.pool_type,
        scope_key=credit.scope_key,
        total_amount_usd=credit.total_amount_usd,
        remaining_amount_usd=credit.remaining_amount_usd,
        expires_at=credit.expires_at,
        reason=credit.reason,
        active=bool(credit.active),
        created_at=credit.created_at,
    )
