from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.modules.governance.domain.security.finding_models import (
    RiskSeverity,
    SecurityAuditReport,
    SecurityFinding,
    severity_weight,
)

_PRIVILEGED_ROLES = {
    "owner",
    "contributor",
    "user access administrator",
    "privileged role administrator",
    "security administrator",
}


class AzureRBACAuditor:
    """Deterministic RBAC posture evaluator for Azure role assignments."""

    def __init__(
        self,
        role_assignments: Sequence[Mapping[str, Any]],
        *,
        subscription_id: str | None = None,
    ) -> None:
        self._role_assignments = role_assignments
        self._subscription_id = str(subscription_id or "").strip()

    async def audit(self) -> SecurityAuditReport:
        findings: list[SecurityFinding] = []

        for assignment in self._role_assignments:
            role_name = str(assignment.get("role_definition_name") or "").strip()
            role_name_lower = role_name.lower()
            principal_name = str(assignment.get("principal_name") or "unknown")
            principal_type = str(assignment.get("principal_type") or "unknown")
            scope = str(assignment.get("scope") or "").strip() or "unknown"
            mfa_enabled = assignment.get("mfa_enabled")
            pim_eligible = assignment.get("is_pim_eligible")

            if role_name_lower in _PRIVILEGED_ROLES:
                severity: RiskSeverity = "high"
                title = f"Privileged Azure role detected: {role_name}"
                detail = (
                    f"{principal_name} holds a privileged role ({role_name}) at scope {scope}."
                )
                recommendation = (
                    "Restrict to least privilege and enforce just-in-time elevation with approval."
                )

                if self._is_broad_scope(scope):
                    severity = "critical"
                    detail = (
                        f"{principal_name} holds {role_name} at broad scope {scope}, "
                        "expanding blast radius across subscriptions/resources."
                    )
                    recommendation = (
                        "Reduce assignment scope and require time-bound elevation for broad roles."
                    )

                findings.append(
                    SecurityFinding(
                        provider="azure",
                        domain="identity",
                        principal=principal_name,
                        control="least_privilege",
                        severity=severity,
                        title=title,
                        detail=detail,
                        recommendation=recommendation,
                        metadata={
                            "principal_type": principal_type,
                            "scope": scope,
                            "role": role_name,
                        },
                    )
                )

                if mfa_enabled is False:
                    findings.append(
                        SecurityFinding(
                            provider="azure",
                            domain="identity",
                            principal=principal_name,
                            control="mfa_enforcement",
                            severity="high",
                            title="Privileged principal without MFA",
                            detail=(
                                f"{principal_name} has privileged access without MFA enforcement."
                            ),
                            recommendation="Require MFA for every privileged principal.",
                            metadata={
                                "principal_type": principal_type,
                                "scope": scope,
                                "role": role_name,
                            },
                        )
                    )

                if pim_eligible is False:
                    findings.append(
                        SecurityFinding(
                            provider="azure",
                            domain="identity",
                            principal=principal_name,
                            control="jit_access",
                            severity="medium",
                            title="Permanent privileged assignment",
                            detail=(
                                f"{principal_name} has permanent privileged assignment ({role_name}) "
                                "without PIM eligibility."
                            ),
                            recommendation=(
                                "Convert permanent privileged assignments to just-in-time eligible roles."
                            ),
                            metadata={
                                "principal_type": principal_type,
                                "scope": scope,
                                "role": role_name,
                            },
                        )
                    )

        score = self._score(findings)
        return SecurityAuditReport(
            provider="azure",
            domain="identity",
            scope=self._scope_label(),
            score=score,
            status="compliant" if score >= 85 else "risk",
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        -severity_weight(finding.severity),
                        finding.principal,
                        finding.title,
                    ),
                )
            ),
            metadata={
                "assignment_count": len(self._role_assignments),
                "privileged_roles_detected": sum(
                    1 for assignment in self._role_assignments
                    if str(assignment.get("role_definition_name") or "").strip().lower()
                    in _PRIVILEGED_ROLES
                ),
            },
        )

    def _scope_label(self) -> str:
        if self._subscription_id:
            return f"subscription:{self._subscription_id}"
        return "subscription:unknown"

    def _is_broad_scope(self, scope: str) -> bool:
        normalized = scope.strip().lower()
        if not normalized:
            return False
        if normalized in {"/", "/subscriptions"}:
            return True
        if normalized.startswith("/providers/microsoft.management/managementgroups"):
            return True
        if normalized.startswith("/subscriptions/") and normalized.count("/") <= 2:
            return True
        return False

    def _score(self, findings: Sequence[SecurityFinding]) -> int:
        score = 100
        for finding in findings:
            score -= severity_weight(finding.severity)
        return max(0, score)
