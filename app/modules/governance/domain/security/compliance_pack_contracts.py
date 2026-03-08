from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CompliancePackActor:
    id: UUID
    email: str
    tenant_id: UUID
    tier: str


@dataclass(frozen=True, slots=True)
class CompliancePackBundleResult:
    body: bytes
    filename: str
    media_type: str = "application/zip"


class CompliancePackValidationError(ValueError):
    """Raised when compliance-pack export inputs fail domain validation."""

