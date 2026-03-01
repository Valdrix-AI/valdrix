from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.governance.domain.security.finding_models import (
    SecurityAuditReport,
    SecurityFinding,
    severity_weight,
)


class DomainAuditor(Protocol):
    async def audit(self) -> SecurityAuditReport:
        """Return a deterministic security report for a single domain/provider."""


@dataclass(frozen=True)
class UnifiedSecurityAuditReport:
    score: int
    status: str
    reports: tuple[SecurityAuditReport, ...] = field(default_factory=tuple)
    findings: tuple[SecurityFinding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "status": self.status,
            "reports": [report.to_dict() for report in self.reports],
            "findings": [finding.to_dict() for finding in self.findings],
        }


class UnifiedDomainAuditor:
    """Aggregates security posture across cloud and SaaS auditors."""

    def __init__(self, auditors: Sequence[DomainAuditor]) -> None:
        self._auditors = tuple(auditors)

    async def audit(self) -> UnifiedSecurityAuditReport:
        if not self._auditors:
            return UnifiedSecurityAuditReport(score=100, status="compliant")

        reports = await asyncio.gather(*(auditor.audit() for auditor in self._auditors))
        ordered_reports = tuple(
            sorted(reports, key=lambda report: (report.provider, report.domain, report.scope))
        )

        findings = tuple(
            sorted(
                (finding for report in ordered_reports for finding in report.findings),
                key=lambda finding: (
                    -severity_weight(finding.severity),
                    finding.provider,
                    finding.principal,
                    finding.title,
                ),
            )
        )

        aggregate_score = round(
            sum(report.score for report in ordered_reports) / max(1, len(ordered_reports))
        )
        has_risk = any(report.status != "compliant" for report in ordered_reports)

        return UnifiedSecurityAuditReport(
            score=max(0, min(100, int(aggregate_score))),
            status="risk" if has_risk else "compliant",
            reports=ordered_reports,
            findings=findings,
        )
