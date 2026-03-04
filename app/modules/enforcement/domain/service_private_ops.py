from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, cast
from uuid import UUID

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementCreditPoolType,
    EnforcementDecision,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.modules.enforcement.domain.approval_routing_ops import (
    default_approval_routing_trace as _default_approval_routing_trace_impl,
    enforce_reviewer_authority as _enforce_reviewer_authority_impl,
    extract_decision_risk_level as _extract_decision_risk_level_impl,
    resolve_approval_routing_trace as _resolve_approval_routing_trace_impl,
    routing_trace_or_default as _routing_trace_or_default_impl,
)
from app.modules.enforcement.domain.approval_token_ops import (
    build_approval_token as _build_approval_token_impl,
    decode_approval_token as _decode_approval_token_impl,
    extract_token_context_payload as _extract_token_context_payload_impl,
)
from app.modules.enforcement.domain.budget_credit_ops import (
    create_credit_grant_for_service as _create_credit_grant_runtime_impl,
    list_budgets_for_service as _list_budgets_runtime_impl,
    list_credits_for_service as _list_credits_runtime_impl,
    upsert_budget_for_service as _upsert_budget_runtime_impl,
)
from app.modules.enforcement.domain.computed_context_ops import (
    build_decision_computed_context_for_service as _build_decision_computed_context_runtime_impl,
    derive_risk_assessment_for_service as _derive_risk_assessment_runtime_impl,
    load_daily_cost_totals_for_service as _load_daily_cost_totals_runtime_impl,
    month_total_days_for_service as _month_total_days_runtime_impl,
    resolve_enterprise_monthly_ceiling_usd_for_service as _resolve_enterprise_monthly_ceiling_usd_runtime_impl,
    resolve_plan_monthly_ceiling_usd_for_service as _resolve_plan_monthly_ceiling_usd_runtime_impl,
    resolve_tenant_tier_for_service as _resolve_tenant_tier_runtime_impl,
)
from app.modules.enforcement.domain.credit_ops import (
    get_credit_headrooms as _get_credit_headrooms_impl,
    reserve_credit_for_decision as _reserve_credit_for_decision_impl,
    reserve_credit_from_grants as _reserve_credit_from_grants_impl,
    settle_credit_reservations_for_decision as _settle_credit_reservations_for_decision_impl,
)
from app.modules.enforcement.domain.policy_contract_ops import (
    apply_policy_contract_materialization as _apply_policy_contract_materialization_impl,
    materialize_policy_contract_payload as _materialize_policy_contract_payload_impl,
    policy_document_contract_backfill_required as _policy_document_contract_backfill_required_impl,
)
from app.modules.enforcement.domain.policy_document import (
    ApprovalRoutingRule,
    POLICY_DOCUMENT_SCHEMA_VERSION,
    PolicyDocument,
    PolicyDocumentApprovalMatrix,
    PolicyDocumentEntitlementMatrix,
    PolicyDocumentExecutionMatrix,
    PolicyDocumentModeMatrix,
    canonical_policy_document_payload,
    policy_document_sha256,
)
from app.modules.enforcement.domain.runtime_query_ops import (
    assert_pending as _assert_pending_impl,
    load_approval_with_decision as _load_approval_with_decision_impl,
)
from app.modules.enforcement.domain.service_models import (
    ApprovalTokenContext,
    EntitlementWaterfallResult,
    PolicyContractMaterialization,
)
from app.modules.enforcement.domain.service_runtime_ops import (
    normalize_policy_approval_routing_rules as _normalize_policy_approval_routing_rules_impl,
    resolve_policy_mode as _resolve_policy_mode_impl,
)
from app.modules.enforcement.domain.service_utils import (
    _DEFAULT_ALLOWED_REVIEWER_ROLES,
    _as_utc,
    _default_required_permission_for_environment,
    _is_production_environment,
    _normalize_allowed_reviewer_roles,
    _normalize_environment,
    _normalize_role_value,
    _normalize_string_list,
    _quantize,
    _to_decimal,
    _utcnow,
)
from app.modules.enforcement.domain.waterfall_ops import (
    evaluate_budget_waterfall as _evaluate_budget_waterfall_impl,
    evaluate_entitlement_waterfall as _evaluate_entitlement_waterfall_impl,
    mode_violation_decision as _mode_violation_decision_impl,
    mode_violation_reason_suffix as _mode_violation_reason_suffix_impl,
)
from app.shared.core.approval_permissions import user_has_approval_permission
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings


class EnforcementServicePrivateOps:
    db: AsyncSession

    _normalize_policy_approval_routing_rules = _normalize_policy_approval_routing_rules_impl
    _resolve_policy_mode = _resolve_policy_mode_impl
    _resolve_tenant_tier = _resolve_tenant_tier_runtime_impl
    _resolve_plan_monthly_ceiling_usd = _resolve_plan_monthly_ceiling_usd_runtime_impl
    _resolve_enterprise_monthly_ceiling_usd = (
        _resolve_enterprise_monthly_ceiling_usd_runtime_impl
    )
    _month_total_days = _month_total_days_runtime_impl
    _load_daily_cost_totals = _load_daily_cost_totals_runtime_impl
    _derive_risk_assessment = _derive_risk_assessment_runtime_impl
    _build_decision_computed_context = _build_decision_computed_context_runtime_impl
    list_budgets = _list_budgets_runtime_impl
    upsert_budget = _upsert_budget_runtime_impl
    list_credits = _list_credits_runtime_impl
    create_credit_grant = _create_credit_grant_runtime_impl

    def _policy_document_contract_backfill_required(
        self,
        policy: EnforcementPolicy,
    ) -> bool:
        return _policy_document_contract_backfill_required_impl(
            policy=policy,
            policy_document_schema_version=POLICY_DOCUMENT_SCHEMA_VERSION,
            canonical_policy_document_payload_fn=canonical_policy_document_payload,
            policy_document_sha256_fn=policy_document_sha256,
        )

    def _materialize_policy_contract(
        self,
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
    ) -> PolicyContractMaterialization:
        payload = _materialize_policy_contract_payload_impl(
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
            enforce_prod_requester_reviewer_separation=(
                enforce_prod_requester_reviewer_separation
            ),
            enforce_nonprod_requester_reviewer_separation=(
                enforce_nonprod_requester_reviewer_separation
            ),
            approval_routing_rules=approval_routing_rules,
            policy_document=policy_document,
            normalize_policy_approval_routing_rules_fn=(
                self._normalize_policy_approval_routing_rules
            ),
            policy_document_model_cls=PolicyDocument,
            policy_document_mode_matrix_cls=PolicyDocumentModeMatrix,
            policy_document_approval_matrix_cls=PolicyDocumentApprovalMatrix,
            policy_document_entitlement_matrix_cls=PolicyDocumentEntitlementMatrix,
            policy_document_execution_matrix_cls=PolicyDocumentExecutionMatrix,
            approval_routing_rule_cls=ApprovalRoutingRule,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
            canonical_policy_document_payload_fn=canonical_policy_document_payload,
            policy_document_sha256_fn=policy_document_sha256,
            policy_document_schema_version=POLICY_DOCUMENT_SCHEMA_VERSION,
        )
        return PolicyContractMaterialization(**payload)

    def _apply_policy_contract_materialization(
        self,
        policy: EnforcementPolicy,
        materialized: PolicyContractMaterialization,
        *,
        increment_policy_version: bool,
    ) -> None:
        _apply_policy_contract_materialization_impl(
            policy=policy,
            materialized=materialized,
            increment_policy_version=increment_policy_version,
        )

    def _default_approval_routing_trace(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
    ) -> dict[str, Any]:
        return _default_approval_routing_trace_impl(
            policy=policy,
            decision=decision,
            normalize_environment_fn=_normalize_environment,
            is_production_environment_fn=_is_production_environment,
            default_required_permission_for_environment_fn=(
                _default_required_permission_for_environment
            ),
            default_allowed_reviewer_roles=_DEFAULT_ALLOWED_REVIEWER_ROLES,
        )

    def _extract_decision_risk_level(self, decision: EnforcementDecision) -> str | None:
        return _extract_decision_risk_level_impl(decision)

    def _resolve_approval_routing_trace(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
    ) -> dict[str, Any]:
        return _resolve_approval_routing_trace_impl(
            policy=policy,
            decision=decision,
            default_approval_routing_trace_fn=self._default_approval_routing_trace,
            extract_decision_risk_level_fn=self._extract_decision_risk_level,
            normalize_environment_fn=_normalize_environment,
            normalize_string_list_fn=_normalize_string_list,
            normalize_allowed_reviewer_roles_fn=_normalize_allowed_reviewer_roles,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
        )

    def _routing_trace_or_default(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
        approval: EnforcementApprovalRequest,
    ) -> dict[str, Any]:
        return _routing_trace_or_default_impl(
            policy=policy,
            decision=decision,
            approval=approval,
            resolve_approval_routing_trace_fn=self._resolve_approval_routing_trace,
            normalize_allowed_reviewer_roles_fn=_normalize_allowed_reviewer_roles,
        )

    async def _enforce_reviewer_authority(
        self,
        *,
        tenant_id: UUID,
        policy: EnforcementPolicy,
        approval: EnforcementApprovalRequest,
        decision: EnforcementDecision,
        reviewer: CurrentUser,
        enforce_requester_separation: bool,
    ) -> dict[str, Any]:
        return await _enforce_reviewer_authority_impl(
            db=self.db,
            tenant_id=tenant_id,
            policy=policy,
            approval=approval,
            decision=decision,
            reviewer=reviewer,
            enforce_requester_separation=enforce_requester_separation,
            routing_trace_or_default_fn=self._routing_trace_or_default,
            normalize_role_value_fn=_normalize_role_value,
            normalize_allowed_reviewer_roles_fn=_normalize_allowed_reviewer_roles,
            user_has_approval_permission_fn=user_has_approval_permission,
        )

    async def _get_credit_headrooms(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
        now: datetime,
    ) -> tuple[Decimal, Decimal]:
        return await _get_credit_headrooms_impl(
            db=self.db,
            tenant_id=tenant_id,
            scope_key=scope_key,
            now=now,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
            as_utc_fn=_as_utc,
        )

    async def _get_active_credit_headroom(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
        now: datetime,
    ) -> Decimal:
        reserved_headroom, emergency_headroom = await self._get_credit_headrooms(
            tenant_id=tenant_id,
            scope_key=scope_key,
            now=now,
        )
        return _quantize(reserved_headroom + emergency_headroom, "0.0001")

    async def _reserve_credit_for_decision(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        scope_key: str,
        reserve_reserved_credit_usd: Decimal,
        reserve_emergency_credit_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        return await _reserve_credit_for_decision_impl(
            tenant_id=tenant_id,
            decision_id=decision_id,
            scope_key=scope_key,
            reserve_reserved_credit_usd=reserve_reserved_credit_usd,
            reserve_emergency_credit_usd=reserve_emergency_credit_usd,
            now=now,
            reserve_credit_from_grants_fn=self._reserve_credit_from_grants,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
        )

    async def _reserve_credit_from_grants(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        scope_key: str,
        pool_type: EnforcementCreditPoolType,
        reserve_target_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        return await _reserve_credit_from_grants_impl(
            db=self.db,
            tenant_id=tenant_id,
            decision_id=decision_id,
            scope_key=scope_key,
            pool_type=pool_type,
            reserve_target_usd=reserve_target_usd,
            now=now,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
        )

    async def _settle_credit_reservations_for_decision(
        self,
        *,
        tenant_id: UUID,
        decision: EnforcementDecision,
        consumed_credit_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        return await _settle_credit_reservations_for_decision_impl(
            db=self.db,
            tenant_id=tenant_id,
            decision=decision,
            consumed_credit_usd=consumed_credit_usd,
            now=now,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
            as_utc_fn=_as_utc,
        )

    def _mode_violation_decision(self, mode: EnforcementMode) -> EnforcementDecisionType:
        return cast(
            EnforcementDecisionType,
            _mode_violation_decision_impl(
                mode=mode,
                shadow_mode=EnforcementMode.SHADOW,
                soft_mode=EnforcementMode.SOFT,
                shadow_decision=EnforcementDecisionType.ALLOW,
                soft_decision=EnforcementDecisionType.REQUIRE_APPROVAL,
                hard_decision=EnforcementDecisionType.DENY,
            ),
        )

    def _mode_violation_reason_suffix(self, mode: EnforcementMode, *, subject: str) -> str:
        return _mode_violation_reason_suffix_impl(
            mode=mode,
            subject=subject,
            shadow_mode=EnforcementMode.SHADOW,
            soft_mode=EnforcementMode.SOFT,
        )

    def _evaluate_entitlement_waterfall(
        self,
        *,
        mode: EnforcementMode,
        monthly_delta: Decimal,
        plan_headroom: Decimal | None,
        allocation_headroom: Decimal | None,
        reserved_credit_headroom: Decimal,
        emergency_credit_headroom: Decimal,
        enterprise_headroom: Decimal | None,
    ) -> EntitlementWaterfallResult:
        payload = _evaluate_entitlement_waterfall_impl(
            mode=mode,
            monthly_delta=monthly_delta,
            plan_headroom=plan_headroom,
            allocation_headroom=allocation_headroom,
            reserved_credit_headroom=reserved_credit_headroom,
            emergency_credit_headroom=emergency_credit_headroom,
            enterprise_headroom=enterprise_headroom,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
            mode_violation_decision_fn=self._mode_violation_decision,
            allow_decision=EnforcementDecisionType.ALLOW,
            allow_with_credits_decision=EnforcementDecisionType.ALLOW_WITH_CREDITS,
            soft_mode=EnforcementMode.SOFT,
        )
        return EntitlementWaterfallResult(**payload)

    def _evaluate_budget_waterfall(
        self,
        *,
        mode: EnforcementMode,
        monthly_delta: Decimal,
        allocation_headroom: Decimal | None,
        credits_headroom: Decimal,
        reasons: list[str],
    ) -> tuple[EnforcementDecisionType, Decimal, Decimal]:
        return _evaluate_budget_waterfall_impl(
            mode=mode,
            monthly_delta=monthly_delta,
            allocation_headroom=allocation_headroom,
            credits_headroom=credits_headroom,
            reasons=reasons,
            evaluate_entitlement_waterfall_fn=self._evaluate_entitlement_waterfall,
            shadow_mode=EnforcementMode.SHADOW,
            soft_mode=EnforcementMode.SOFT,
        )

    _load_approval_with_decision = _load_approval_with_decision_impl
    _assert_pending = _assert_pending_impl

    def _decode_approval_token(self, approval_token: str) -> Mapping[str, Any]:
        return _decode_approval_token_impl(
            approval_token,
            get_settings_fn=get_settings,
            jwt_module=jwt,
        )

    def _extract_token_context(
        self,
        payload: Mapping[str, Any],
    ) -> ApprovalTokenContext:
        context_payload = _extract_token_context_payload_impl(
            payload,
            source_enum=EnforcementSource,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
        )
        return ApprovalTokenContext(**context_payload)

    def _build_approval_token(
        self,
        *,
        decision: EnforcementDecision,
        approval: EnforcementApprovalRequest,
        expires_at: datetime,
    ) -> str:
        return _build_approval_token_impl(
            decision=decision,
            approval=approval,
            expires_at=expires_at,
            get_settings_fn=get_settings,
            utcnow_fn=_utcnow,
            to_decimal_fn=_to_decimal,
            jwt_module=jwt,
        )
