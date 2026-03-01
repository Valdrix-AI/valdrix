from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.modules.governance.domain.security.finding_models import (
    SecurityAuditReport,
    SecurityFinding,
    severity_weight,
)

_PRIVILEGED_ROLES = {
    "roles/owner",
    "roles/editor",
    "roles/resourcemanager.projectiamadmin",
    "roles/iam.securityadmin",
    "roles/iam.serviceaccountadmin",
}

_PUBLIC_MEMBERS = {"allusers", "allauthenticatedusers"}


class GCPIAMAuditor:
    """Deterministic IAM posture evaluator for GCP role bindings."""

    def __init__(
        self,
        iam_bindings: Sequence[Mapping[str, Any]],
        *,
        project_id: str | None = None,
    ) -> None:
        self._iam_bindings = iam_bindings
        self._project_id = str(project_id or "").strip()

    async def audit(self) -> SecurityAuditReport:
        findings: list[SecurityFinding] = []

        for binding in self._iam_bindings:
            role = str(binding.get("role") or "").strip()
            role_lower = role.lower()
            members_raw = binding.get("members")
            members = (
                [str(member) for member in members_raw]
                if isinstance(members_raw, list)
                else [str(members_raw)] if members_raw
                else []
            )
            condition = binding.get("condition")
            condition_present = bool(condition)

            public_members = [
                member
                for member in members
                if member.strip().lower() in _PUBLIC_MEMBERS
            ]
            for member in public_members:
                findings.append(
                    SecurityFinding(
                        provider="gcp",
                        domain="identity",
                        principal=member,
                        control="public_access",
                        severity="critical",
                        title="Public IAM membership detected",
                        detail=(
                            f"Binding grants role {role or 'unknown'} to public principal {member}."
                        ),
                        recommendation="Remove public members and scope access to explicit identities.",
                        metadata={"role": role, "member": member},
                    )
                )

            if role_lower in _PRIVILEGED_ROLES:
                for member in members:
                    findings.append(
                        SecurityFinding(
                            provider="gcp",
                            domain="identity",
                            principal=member,
                            control="least_privilege",
                            severity="high",
                            title=f"Privileged GCP role detected: {role}",
                            detail=(
                                f"Principal {member} has privileged role {role}."
                            ),
                            recommendation=(
                                "Reduce role scope and replace broad roles with least-privilege custom roles."
                            ),
                            metadata={
                                "role": role,
                                "condition_present": condition_present,
                            },
                        )
                    )

                    if not condition_present:
                        findings.append(
                            SecurityFinding(
                                provider="gcp",
                                domain="identity",
                                principal=member,
                                control="conditional_access",
                                severity="medium",
                                title="Privileged binding without condition",
                                detail=(
                                    f"Privileged role {role} for {member} has no IAM condition guardrail."
                                ),
                                recommendation=(
                                    "Add IAM conditions (time/resource constraints) for privileged bindings."
                                ),
                                metadata={"role": role},
                            )
                        )

        score = self._score(findings)
        return SecurityAuditReport(
            provider="gcp",
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
                "binding_count": len(self._iam_bindings),
                "privileged_binding_count": sum(
                    1
                    for binding in self._iam_bindings
                    if str(binding.get("role") or "").strip().lower() in _PRIVILEGED_ROLES
                ),
            },
        )

    def _scope_label(self) -> str:
        if self._project_id:
            return f"project:{self._project_id}"
        return "project:unknown"

    def _score(self, findings: Sequence[SecurityFinding]) -> int:
        score = 100
        for finding in findings:
            score -= severity_weight(finding.severity)
        return max(0, score)
