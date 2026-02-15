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

    def evaluate(
        self, request: RemediationRequest, config: PolicyConfig | None = None
    ) -> PolicyEvaluation:
        active_config = config or PolicyConfig()
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
        text = " ".join(
            str(v or "")
            for v in (
                getattr(request, "resource_id", ""),
                getattr(request, "resource_type", ""),
                getattr(request, "explainability_notes", ""),
            )
        ).lower()
        return any(marker in text for marker in self._PRODUCTION_MARKERS)

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
        return {
            "request_id": str(getattr(request, "id", "")),
            "tenant_id": str(getattr(request, "tenant_id", "")),
            "resource_id": str(getattr(request, "resource_id", "")),
            "resource_type": str(getattr(request, "resource_type", "")),
            "action": action_value,
            "requested_by_user_id": str(getattr(request, "requested_by_user_id", "")),
            "reviewed_by_user_id": str(getattr(request, "reviewed_by_user_id", "")),
        }
