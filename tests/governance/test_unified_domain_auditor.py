from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.modules.governance.domain.security.finding_models import (
    SecurityAuditReport,
    SecurityFinding,
)
from app.modules.governance.domain.security.unified_domain_auditor import (
    UnifiedDomainAuditor,
)


@dataclass
class _StubAuditor:
    report: SecurityAuditReport

    async def audit(self) -> SecurityAuditReport:
        return self.report


@pytest.mark.asyncio
async def test_unified_domain_auditor_aggregates_and_sorts_findings() -> None:
    azure_report = SecurityAuditReport(
        provider="azure",
        domain="identity",
        scope="subscription:sub-a",
        score=70,
        status="risk",
        findings=(
            SecurityFinding(
                provider="azure",
                domain="identity",
                principal="alice",
                control="least_privilege",
                severity="high",
                title="Privileged role",
                detail="d",
                recommendation="r",
            ),
        ),
    )
    gcp_report = SecurityAuditReport(
        provider="gcp",
        domain="identity",
        scope="project:prod",
        score=95,
        status="compliant",
        findings=(
            SecurityFinding(
                provider="gcp",
                domain="identity",
                principal="allUsers",
                control="public_access",
                severity="critical",
                title="Public member",
                detail="d",
                recommendation="r",
            ),
        ),
    )

    auditor = UnifiedDomainAuditor([_StubAuditor(gcp_report), _StubAuditor(azure_report)])
    report = await auditor.audit()

    assert report.status == "risk"
    assert report.score == 82  # round((70 + 95) / 2)
    assert [r.provider for r in report.reports] == ["azure", "gcp"]
    assert [f.severity for f in report.findings] == ["critical", "high"]


@pytest.mark.asyncio
async def test_unified_domain_auditor_empty_set_is_compliant() -> None:
    report = await UnifiedDomainAuditor([]).audit()
    assert report.status == "compliant"
    assert report.score == 100
    assert report.reports == ()
    assert report.findings == ()
