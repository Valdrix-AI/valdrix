from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import EnforcementMode, EnforcementPolicy


def policy_document_contract_backfill_required(
    *,
    policy: EnforcementPolicy,
    policy_document_schema_version: str,
    canonical_policy_document_payload_fn: Callable[[Any], dict[str, Any]],
    policy_document_sha256_fn: Callable[[Any], str],
) -> bool:
    schema_version = str(getattr(policy, "policy_document_schema_version", "")).strip()
    if schema_version != policy_document_schema_version:
        return True

    policy_document_raw = getattr(policy, "policy_document", None)
    if not isinstance(policy_document_raw, Mapping):
        return True

    try:
        canonical_payload = canonical_policy_document_payload_fn(policy_document_raw)
    except (ValidationError, TypeError):
        return True

    hash_raw = str(getattr(policy, "policy_document_sha256", "")).strip().lower()
    if len(hash_raw) != 64 or any(ch not in "0123456789abcdef" for ch in hash_raw):
        return True
    return hash_raw != policy_document_sha256_fn(canonical_payload)


def materialize_policy_contract_payload(
    *,
    terraform_mode: EnforcementMode,
    terraform_mode_prod: EnforcementMode | None,
    terraform_mode_nonprod: EnforcementMode | None,
    k8s_admission_mode: EnforcementMode,
    k8s_admission_mode_prod: EnforcementMode | None,
    k8s_admission_mode_nonprod: EnforcementMode | None,
    require_approval_for_prod: bool,
    require_approval_for_nonprod: bool,
    plan_monthly_ceiling_usd: Decimal | None,
    enterprise_monthly_ceiling_usd: Decimal | None,
    auto_approve_below_monthly_usd: Decimal,
    hard_deny_above_monthly_usd: Decimal,
    default_ttl_seconds: int,
    enforce_prod_requester_reviewer_separation: bool,
    enforce_nonprod_requester_reviewer_separation: bool,
    approval_routing_rules: list[Mapping[str, Any]] | None,
    policy_document: Mapping[str, Any] | None,
    normalize_policy_approval_routing_rules_fn: Callable[[list[Mapping[str, Any]] | None], list[dict[str, Any]]],
    policy_document_model_cls: type[Any],
    policy_document_mode_matrix_cls: type[Any],
    policy_document_approval_matrix_cls: type[Any],
    policy_document_entitlement_matrix_cls: type[Any],
    policy_document_execution_matrix_cls: type[Any],
    approval_routing_rule_cls: type[Any],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[..., Decimal],
    canonical_policy_document_payload_fn: Callable[[Any], dict[str, Any]],
    policy_document_sha256_fn: Callable[[Any], str],
    policy_document_schema_version: str,
) -> dict[str, Any]:
    if policy_document is not None:
        try:
            document_model = policy_document_model_cls.model_validate(policy_document)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "policy_document is invalid",
                    "errors": exc.errors(),
                },
            ) from exc

        normalized_routing_rules = normalize_policy_approval_routing_rules_fn(
            [rule.model_dump(mode="json") for rule in document_model.approval.routing_rules]
        )
    else:
        normalized_routing_rules = normalize_policy_approval_routing_rules_fn(
            approval_routing_rules
        )
        document_model = policy_document_model_cls(
            mode_matrix=policy_document_mode_matrix_cls(
                terraform_default=terraform_mode,
                terraform_prod=terraform_mode_prod or terraform_mode,
                terraform_nonprod=terraform_mode_nonprod or terraform_mode,
                k8s_admission_default=k8s_admission_mode,
                k8s_admission_prod=k8s_admission_mode_prod or k8s_admission_mode,
                k8s_admission_nonprod=(
                    k8s_admission_mode_nonprod or k8s_admission_mode
                ),
            ),
            approval=policy_document_approval_matrix_cls(
                require_approval_prod=bool(require_approval_for_prod),
                require_approval_nonprod=bool(require_approval_for_nonprod),
                enforce_prod_requester_reviewer_separation=bool(
                    enforce_prod_requester_reviewer_separation
                ),
                enforce_nonprod_requester_reviewer_separation=bool(
                    enforce_nonprod_requester_reviewer_separation
                ),
                routing_rules=[
                    approval_routing_rule_cls.model_validate(rule)
                    for rule in normalized_routing_rules
                ],
            ),
            entitlements=policy_document_entitlement_matrix_cls(
                plan_monthly_ceiling_usd=plan_monthly_ceiling_usd,
                enterprise_monthly_ceiling_usd=enterprise_monthly_ceiling_usd,
                auto_approve_below_monthly_usd=auto_approve_below_monthly_usd,
                hard_deny_above_monthly_usd=hard_deny_above_monthly_usd,
            ),
            execution=policy_document_execution_matrix_cls(
                default_ttl_seconds=max(60, min(int(default_ttl_seconds), 86400))
            ),
        )

    auto_approve_threshold = quantize_fn(
        to_decimal_fn(document_model.entitlements.auto_approve_below_monthly_usd),
        "0.0001",
    )
    hard_deny_threshold = quantize_fn(
        to_decimal_fn(document_model.entitlements.hard_deny_above_monthly_usd),
        "0.0001",
    )
    if hard_deny_threshold <= Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="hard_deny_above_monthly_usd must be greater than 0",
        )
    if auto_approve_threshold < Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="auto_approve_below_monthly_usd must be >= 0",
        )
    if auto_approve_threshold > hard_deny_threshold:
        raise HTTPException(
            status_code=422,
            detail=(
                "auto_approve_below_monthly_usd cannot exceed "
                "hard_deny_above_monthly_usd"
            ),
        )

    plan_ceiling = (
        quantize_fn(to_decimal_fn(document_model.entitlements.plan_monthly_ceiling_usd), "0.0001")
        if document_model.entitlements.plan_monthly_ceiling_usd is not None
        else None
    )
    enterprise_ceiling = (
        quantize_fn(
            to_decimal_fn(document_model.entitlements.enterprise_monthly_ceiling_usd),
            "0.0001",
        )
        if document_model.entitlements.enterprise_monthly_ceiling_usd is not None
        else None
    )
    if plan_ceiling is not None and plan_ceiling < Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="plan_monthly_ceiling_usd must be >= 0 when provided",
        )
    if enterprise_ceiling is not None and enterprise_ceiling < Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="enterprise_monthly_ceiling_usd must be >= 0 when provided",
        )

    materialized_document = policy_document_model_cls(
        mode_matrix=document_model.mode_matrix,
        approval=policy_document_approval_matrix_cls(
            require_approval_prod=bool(document_model.approval.require_approval_prod),
            require_approval_nonprod=bool(document_model.approval.require_approval_nonprod),
            enforce_prod_requester_reviewer_separation=bool(
                document_model.approval.enforce_prod_requester_reviewer_separation
            ),
            enforce_nonprod_requester_reviewer_separation=bool(
                document_model.approval.enforce_nonprod_requester_reviewer_separation
            ),
            routing_rules=[
                approval_routing_rule_cls.model_validate(item)
                for item in normalized_routing_rules
            ],
        ),
        entitlements=policy_document_entitlement_matrix_cls(
            plan_monthly_ceiling_usd=plan_ceiling,
            enterprise_monthly_ceiling_usd=enterprise_ceiling,
            auto_approve_below_monthly_usd=auto_approve_threshold,
            hard_deny_above_monthly_usd=hard_deny_threshold,
        ),
        execution=policy_document_execution_matrix_cls(
            default_ttl_seconds=max(
                60,
                min(int(document_model.execution.default_ttl_seconds), 86400),
            ),
            action_max_attempts=max(
                1,
                min(int(document_model.execution.action_max_attempts), 10),
            ),
            action_retry_backoff_seconds=max(
                1,
                min(int(document_model.execution.action_retry_backoff_seconds), 86400),
            ),
            action_lease_ttl_seconds=max(
                30,
                min(int(document_model.execution.action_lease_ttl_seconds), 3600),
            ),
        ),
    )
    canonical_document = canonical_policy_document_payload_fn(materialized_document)
    document_hash = policy_document_sha256_fn(canonical_document)

    return {
        "terraform_mode": materialized_document.mode_matrix.terraform_default,
        "terraform_mode_prod": materialized_document.mode_matrix.terraform_prod,
        "terraform_mode_nonprod": materialized_document.mode_matrix.terraform_nonprod,
        "k8s_admission_mode": materialized_document.mode_matrix.k8s_admission_default,
        "k8s_admission_mode_prod": materialized_document.mode_matrix.k8s_admission_prod,
        "k8s_admission_mode_nonprod": materialized_document.mode_matrix.k8s_admission_nonprod,
        "require_approval_for_prod": bool(
            materialized_document.approval.require_approval_prod
        ),
        "require_approval_for_nonprod": bool(
            materialized_document.approval.require_approval_nonprod
        ),
        "enforce_prod_requester_reviewer_separation": bool(
            materialized_document.approval.enforce_prod_requester_reviewer_separation
        ),
        "enforce_nonprod_requester_reviewer_separation": bool(
            materialized_document.approval.enforce_nonprod_requester_reviewer_separation
        ),
        "plan_monthly_ceiling_usd": plan_ceiling,
        "enterprise_monthly_ceiling_usd": enterprise_ceiling,
        "auto_approve_below_monthly_usd": auto_approve_threshold,
        "hard_deny_above_monthly_usd": hard_deny_threshold,
        "default_ttl_seconds": max(
            60,
            min(int(materialized_document.execution.default_ttl_seconds), 86400),
        ),
        "approval_routing_rules": normalized_routing_rules,
        "policy_document_schema_version": policy_document_schema_version,
        "policy_document_sha256": document_hash,
        "policy_document": canonical_document,
    }


def apply_policy_contract_materialization(
    *,
    policy: EnforcementPolicy,
    materialized: Any,
    increment_policy_version: bool,
) -> None:
    policy.terraform_mode = materialized.terraform_mode
    policy.terraform_mode_prod = materialized.terraform_mode_prod
    policy.terraform_mode_nonprod = materialized.terraform_mode_nonprod
    policy.k8s_admission_mode = materialized.k8s_admission_mode
    policy.k8s_admission_mode_prod = materialized.k8s_admission_mode_prod
    policy.k8s_admission_mode_nonprod = materialized.k8s_admission_mode_nonprod
    policy.require_approval_for_prod = materialized.require_approval_for_prod
    policy.require_approval_for_nonprod = materialized.require_approval_for_nonprod
    policy.enforce_prod_requester_reviewer_separation = (
        materialized.enforce_prod_requester_reviewer_separation
    )
    policy.enforce_nonprod_requester_reviewer_separation = (
        materialized.enforce_nonprod_requester_reviewer_separation
    )
    policy.plan_monthly_ceiling_usd = materialized.plan_monthly_ceiling_usd
    policy.enterprise_monthly_ceiling_usd = materialized.enterprise_monthly_ceiling_usd
    policy.auto_approve_below_monthly_usd = materialized.auto_approve_below_monthly_usd
    policy.hard_deny_above_monthly_usd = materialized.hard_deny_above_monthly_usd
    policy.default_ttl_seconds = materialized.default_ttl_seconds
    policy.approval_routing_rules = materialized.approval_routing_rules
    policy.policy_document_schema_version = materialized.policy_document_schema_version
    policy.policy_document_sha256 = materialized.policy_document_sha256
    policy.policy_document = materialized.policy_document
    if increment_policy_version:
        policy.policy_version += 1


async def get_or_create_policy(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    policy_document_contract_backfill_required_fn: Callable[[EnforcementPolicy], bool],
    materialize_policy_contract_fn: Callable[..., Any],
    apply_policy_contract_materialization_fn: Callable[..., None],
    to_decimal_fn: Callable[..., Decimal],
) -> EnforcementPolicy:
    policy = (
        await db.execute(select(EnforcementPolicy).where(EnforcementPolicy.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if policy is None:
        policy = EnforcementPolicy(tenant_id=tenant_id)
        db.add(policy)
        await db.flush()

    if policy_document_contract_backfill_required_fn(policy):
        materialized = materialize_policy_contract_fn(
            terraform_mode=policy.terraform_mode or EnforcementMode.SOFT,
            terraform_mode_prod=policy.terraform_mode_prod or EnforcementMode.SOFT,
            terraform_mode_nonprod=policy.terraform_mode_nonprod or EnforcementMode.SOFT,
            k8s_admission_mode=policy.k8s_admission_mode or EnforcementMode.SOFT,
            k8s_admission_mode_prod=policy.k8s_admission_mode_prod or EnforcementMode.SOFT,
            k8s_admission_mode_nonprod=policy.k8s_admission_mode_nonprod or EnforcementMode.SOFT,
            require_approval_for_prod=bool(policy.require_approval_for_prod),
            require_approval_for_nonprod=bool(policy.require_approval_for_nonprod),
            plan_monthly_ceiling_usd=policy.plan_monthly_ceiling_usd,
            enterprise_monthly_ceiling_usd=policy.enterprise_monthly_ceiling_usd,
            auto_approve_below_monthly_usd=to_decimal_fn(
                policy.auto_approve_below_monthly_usd,
                default=Decimal("25"),
            ),
            hard_deny_above_monthly_usd=to_decimal_fn(
                policy.hard_deny_above_monthly_usd,
                default=Decimal("5000"),
            ),
            default_ttl_seconds=int(policy.default_ttl_seconds or 900),
            enforce_prod_requester_reviewer_separation=bool(
                policy.enforce_prod_requester_reviewer_separation
            ),
            enforce_nonprod_requester_reviewer_separation=bool(
                policy.enforce_nonprod_requester_reviewer_separation
            ),
            approval_routing_rules=(
                list(policy.approval_routing_rules)
                if isinstance(policy.approval_routing_rules, list)
                else []
            ),
            policy_document=(
                cast(Mapping[str, Any], policy.policy_document)
                if isinstance(policy.policy_document, Mapping)
                else None
            ),
        )
        apply_policy_contract_materialization_fn(
            policy=policy,
            materialized=materialized,
            increment_policy_version=False,
        )

    await db.flush()
    return policy


async def update_policy(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    terraform_mode: EnforcementMode,
    terraform_mode_prod: EnforcementMode | None,
    terraform_mode_nonprod: EnforcementMode | None,
    k8s_admission_mode: EnforcementMode,
    k8s_admission_mode_prod: EnforcementMode | None,
    k8s_admission_mode_nonprod: EnforcementMode | None,
    require_approval_for_prod: bool,
    require_approval_for_nonprod: bool,
    plan_monthly_ceiling_usd: Decimal | None,
    enterprise_monthly_ceiling_usd: Decimal | None,
    auto_approve_below_monthly_usd: Decimal,
    hard_deny_above_monthly_usd: Decimal,
    default_ttl_seconds: int,
    enforce_prod_requester_reviewer_separation: bool,
    enforce_nonprod_requester_reviewer_separation: bool,
    approval_routing_rules: list[Mapping[str, Any]] | None,
    policy_document: Mapping[str, Any] | None,
    get_or_create_policy_fn: Callable[[UUID], Any],
    materialize_policy_contract_fn: Callable[..., Any],
    apply_policy_contract_materialization_fn: Callable[..., None],
) -> EnforcementPolicy:
    materialized = materialize_policy_contract_fn(
        terraform_mode=terraform_mode,
        terraform_mode_prod=terraform_mode_prod,
        terraform_mode_nonprod=terraform_mode_nonprod,
        k8s_admission_mode=k8s_admission_mode,
        k8s_admission_mode_prod=k8s_admission_mode_prod,
        k8s_admission_mode_nonprod=k8s_admission_mode_nonprod,
        require_approval_for_prod=require_approval_for_prod,
        require_approval_for_nonprod=require_approval_for_nonprod,
        plan_monthly_ceiling_usd=plan_monthly_ceiling_usd,
        enterprise_monthly_ceiling_usd=enterprise_monthly_ceiling_usd,
        auto_approve_below_monthly_usd=auto_approve_below_monthly_usd,
        hard_deny_above_monthly_usd=hard_deny_above_monthly_usd,
        default_ttl_seconds=default_ttl_seconds,
        enforce_prod_requester_reviewer_separation=enforce_prod_requester_reviewer_separation,
        enforce_nonprod_requester_reviewer_separation=enforce_nonprod_requester_reviewer_separation,
        approval_routing_rules=approval_routing_rules,
        policy_document=policy_document,
    )

    policy = cast(EnforcementPolicy, await get_or_create_policy_fn(tenant_id))
    apply_policy_contract_materialization_fn(
        policy=policy,
        materialized=materialized,
        increment_policy_version=True,
    )
    await db.commit()
    await db.refresh(policy)
    return policy
