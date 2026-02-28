"""
Deterministic remediation policy engine.

This module enforces execution-time policy decisions for remediation requests:
- allow: proceed
- warn: proceed with warning audit trail
- block: deny execution
- escalate: deny execution pending stronger approval workflow
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Any

from app.models.remediation import RemediationAction, RemediationRequest


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class PolicyRuleHit:
    rule_id: str
    decision: PolicyDecision
    message: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "decision": self.decision.value,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecision
    rule_hits: tuple[PolicyRuleHit, ...] = ()

    @property
    def summary(self) -> str:
        return (
            self.rule_hits[0].message
            if self.rule_hits
            else "No policy rules triggered."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "summary": self.summary,
            "rule_hits": [hit.to_dict() for hit in self.rule_hits],
        }


@dataclass(frozen=True)
class PolicyConfig:
    enabled: bool = True
    block_production_destructive: bool = True
    require_gpu_override: bool = True
    low_confidence_warn_threshold: Decimal = Decimal("0.90")


class RemediationPolicyEngine:
    """
    Deterministic policy checks for execution safety.

    Precedence:
    1. block
    2. escalate
    3. warn
    4. allow
    """

    _PRODUCTION_MARKERS = ("prod", "production", "critical", "pci", "hipaa")
    _DESTRUCTIVE_ACTIONS = frozenset(
        {
            RemediationAction.DELETE_VOLUME,
            RemediationAction.DELETE_SNAPSHOT,
            RemediationAction.DELETE_S3_BUCKET,
            RemediationAction.DELETE_ECR_IMAGE,
            RemediationAction.DELETE_SAGEMAKER_ENDPOINT,
            RemediationAction.DELETE_REDSHIFT_CLUSTER,
            RemediationAction.DELETE_RDS_INSTANCE,
            RemediationAction.DELETE_NAT_GATEWAY,
            RemediationAction.DELETE_LOAD_BALANCER,
            RemediationAction.TERMINATE_INSTANCE,
        }
    )

    _GPU_APPROVAL_ACTIONS = frozenset(
        {
            RemediationAction.STOP_INSTANCE,
            RemediationAction.TERMINATE_INSTANCE,
            RemediationAction.RESIZE_INSTANCE,
            RemediationAction.DELETE_SAGEMAKER_ENDPOINT,
        }
    )

    _GPU_OVERRIDE_MARKERS = ("gpu-approved", "gpu_override", "approved_gpu")
    _SYSTEM_POLICY_CONTEXT_KEY = "_system_policy_context"

    def evaluate(
        self,
        request: RemediationRequest,
        config: PolicyConfig | None = None,
        is_production: bool = False,
    ) -> PolicyEvaluation:
        active_config = config or PolicyConfig()
        self._is_production_override = is_production
        if not active_config.enabled:
            return PolicyEvaluation(decision=PolicyDecision.ALLOW)

        block_hits = self._evaluate_block_rules(request, active_config)
        if block_hits:
            return PolicyEvaluation(
                decision=PolicyDecision.BLOCK, rule_hits=tuple(block_hits)
            )

        escalate_hits = self._evaluate_escalation_rules(request, active_config)
        if escalate_hits:
            return PolicyEvaluation(
                decision=PolicyDecision.ESCALATE, rule_hits=tuple(escalate_hits)
            )

        warn_hits = self._evaluate_warning_rules(request, active_config)
        if warn_hits:
            return PolicyEvaluation(
                decision=PolicyDecision.WARN, rule_hits=tuple(warn_hits)
            )

        return PolicyEvaluation(decision=PolicyDecision.ALLOW)

    def _evaluate_block_rules(
        self, request: RemediationRequest, config: PolicyConfig
    ) -> list[PolicyRuleHit]:
        if (
            config.block_production_destructive
            and self._is_destructive(request)
            and self._looks_like_production(request)
        ):
            return [
                PolicyRuleHit(
                    rule_id="protect-production-destructive",
                    decision=PolicyDecision.BLOCK,
                    message="Destructive remediation blocked for production-like resource identifiers.",
                    evidence=self._base_evidence(request),
                )
            ]
        return []

    def _evaluate_escalation_rules(
        self, request: RemediationRequest, config: PolicyConfig
    ) -> list[PolicyRuleHit]:
        if (
            config.require_gpu_override
            and self._is_gpu_sensitive(request)
            and not self._has_gpu_override(request)
        ):
            return [
                PolicyRuleHit(
                    rule_id="gpu-change-requires-explicit-override",
                    decision=PolicyDecision.ESCALATE,
                    message="GPU-related remediation requires explicit GPU approval override.",
                    evidence=self._base_evidence(request),
                )
            ]
        return []

    def _evaluate_warning_rules(
        self, request: RemediationRequest, config: PolicyConfig
    ) -> list[PolicyRuleHit]:
        confidence_raw = getattr(request, "confidence_score", None)
        if confidence_raw is None:
            return []

        try:
            confidence = Decimal(str(confidence_raw))
        except Exception:
            return [
                PolicyRuleHit(
                    rule_id="invalid-confidence-score",
                    decision=PolicyDecision.WARN,
                    message="Confidence score is invalid; execution allowed with warning.",
                    evidence=self._base_evidence(request),
                )
            ]

        if confidence < config.low_confidence_warn_threshold:
            evidence = self._base_evidence(request)
            evidence["confidence_score"] = str(confidence)
            evidence["threshold"] = str(config.low_confidence_warn_threshold)
            return [
                PolicyRuleHit(
                    rule_id="low-confidence-remediation",
                    decision=PolicyDecision.WARN,
                    message="Low-confidence remediation execution; review recommended.",
                    evidence=evidence,
                )
            ]
        return []

    def _is_destructive(self, request: RemediationRequest) -> bool:
        action = getattr(request, "action", None)
        return (
            isinstance(action, RemediationAction)
            and action in self._DESTRUCTIVE_ACTIONS
        )

    def _looks_like_production(self, request: RemediationRequest) -> bool:
        # SEC-HAR-12: Priority check on explicit flag
        if getattr(self, "_is_production_override", False):
            return True

        explicit_signal = self._production_signal_from_context(request)
        if explicit_signal is not None:
            return explicit_signal

        text = " ".join(
            str(v or "")
            for v in (
                getattr(request, "resource_id", ""),
                getattr(request, "resource_type", ""),
                getattr(request, "explainability_notes", ""),
            )
        ).lower()
        return any(marker in text for marker in self._PRODUCTION_MARKERS)

    def _production_signal_from_context(
        self, request: RemediationRequest
    ) -> bool | None:
        context = self._trusted_policy_context(request)
        if not context:
            return None

        is_production_raw = context.get("is_production")
        is_production = self._coerce_bool(is_production_raw)
        if is_production is not None:
            return is_production

        environment_raw = context.get("environment")
        if isinstance(environment_raw, str):
            normalized_env = environment_raw.strip().lower()
            if normalized_env in {"prod", "production", "live"}:
                return True
            if normalized_env in {"dev", "development", "staging", "stage", "test"}:
                return False

        return None

    def _trusted_policy_context(self, request: RemediationRequest) -> dict[str, Any]:
        action_parameters = getattr(request, "action_parameters", None)
        if not isinstance(action_parameters, dict):
            return {}

        raw_context = action_parameters.get(self._SYSTEM_POLICY_CONTEXT_KEY)
        if not isinstance(raw_context, dict):
            return {}

        return raw_context

    def _coerce_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return None

    def _is_gpu_sensitive(self, request: RemediationRequest) -> bool:
        action = getattr(request, "action", None)
        if (
            not isinstance(action, RemediationAction)
            or action not in self._GPU_APPROVAL_ACTIONS
        ):
            return False

        text = " ".join(
            str(v or "")
            for v in (
                getattr(request, "resource_id", ""),
                getattr(request, "resource_type", ""),
                getattr(request, "explainability_notes", ""),
            )
        ).lower()
        return bool(re.search(r"\bgpu\b", text))

    def _has_gpu_override(self, request: RemediationRequest) -> bool:
        notes = str(getattr(request, "review_notes", "") or "").lower()
        return any(marker in notes for marker in self._GPU_OVERRIDE_MARKERS)

    def _base_evidence(self, request: RemediationRequest) -> dict[str, Any]:
        action = getattr(request, "action", None)
        action_value = (
            action.value if isinstance(action, RemediationAction) else str(action)
        )
        evidence: dict[str, Any] = {
            "request_id": str(getattr(request, "id", "")),
            "tenant_id": str(getattr(request, "tenant_id", "")),
            "resource_id": str(getattr(request, "resource_id", "")),
            "resource_type": str(getattr(request, "resource_type", "")),
            "action": action_value,
            "requested_by_user_id": str(getattr(request, "requested_by_user_id", "")),
            "reviewed_by_user_id": str(getattr(request, "reviewed_by_user_id", "")),
        }
        context = self._trusted_policy_context(request)
        if context:
            evidence["policy_context"] = {
                "source": context.get("source"),
                "is_production": context.get("is_production"),
                "criticality": context.get("criticality"),
                "environment": context.get("environment"),
            }
        return evidence


def is_production_destructive_remediation(request: RemediationRequest) -> bool:
    """
    Classify whether a remediation targets a production-like resource with a
    destructive action. Used by human-approval authorization controls.
    """
    engine = RemediationPolicyEngine()
    return engine._is_destructive(request) and engine._looks_like_production(request)


def is_production_remediation_target(request: RemediationRequest) -> bool:
    """
    Classify whether a remediation targets a production-like environment.
    Used for tier boundaries that only allow non-production auto-remediation.
    """
    engine = RemediationPolicyEngine()
    return engine._looks_like_production(request)
