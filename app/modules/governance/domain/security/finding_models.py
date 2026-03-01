from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RiskSeverity = Literal["critical", "high", "medium", "low"]

_SEVERITY_WEIGHT: dict[RiskSeverity, int] = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 4,
}


def severity_weight(severity: RiskSeverity) -> int:
    return _SEVERITY_WEIGHT[severity]


@dataclass(frozen=True)
class SecurityFinding:
    provider: str
    domain: str
    principal: str
    control: str
    severity: RiskSeverity
    title: str
    detail: str
    recommendation: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "domain": self.domain,
            "principal": self.principal,
            "control": self.control,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "recommendation": self.recommendation,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SecurityAuditReport:
    provider: str
    domain: str
    scope: str
    score: int
    status: str
    findings: tuple[SecurityFinding, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "domain": self.domain,
            "scope": self.scope,
            "score": self.score,
            "status": self.status,
            "findings": [finding.to_dict() for finding in self.findings],
            "metadata": self.metadata,
        }
