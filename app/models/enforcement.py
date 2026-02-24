from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    event,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EnforcementSource(str, Enum):
    TERRAFORM = "terraform"
    K8S_ADMISSION = "k8s_admission"
    CLOUD_EVENT = "cloud_event"


class EnforcementMode(str, Enum):
    SHADOW = "shadow"
    SOFT = "soft"
    HARD = "hard"


class EnforcementDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ALLOW_WITH_CREDITS = "ALLOW_WITH_CREDITS"


class EnforcementApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class EnforcementPolicy(Base):
    __tablename__ = "enforcement_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_enforcement_policy_tenant"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    terraform_mode: Mapped[EnforcementMode] = mapped_column(
        SQLEnum(
            EnforcementMode, name="enforcement_mode", native_enum=False
        ),
        nullable=False,
        default=EnforcementMode.SOFT,
    )
    k8s_admission_mode: Mapped[EnforcementMode] = mapped_column(
        SQLEnum(
            EnforcementMode, name="enforcement_mode", native_enum=False
        ),
        nullable=False,
        default=EnforcementMode.SOFT,
    )
    require_approval_for_prod: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    require_approval_for_nonprod: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    auto_approve_below_monthly_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("25.0")
    )
    hard_deny_above_monthly_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("5000.0")
    )
    default_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class EnforcementBudgetAllocation(Base):
    __tablename__ = "enforcement_budget_allocations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_key",
            name="uq_enforcement_budget_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    monthly_limit_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class EnforcementCreditGrant(Base):
    __tablename__ = "enforcement_credit_grants"
    __table_args__ = (
        Index(
            "ix_enforcement_credit_scope_active_expiry",
            "tenant_id",
            "scope_key",
            "active",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    total_amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    remaining_amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class EnforcementDecision(Base):
    __tablename__ = "enforcement_decisions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source",
            "idempotency_key",
            name="uq_enforcement_decision_idempotency",
        ),
        Index("ix_enforcement_decision_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[EnforcementSource] = mapped_column(
        SQLEnum(
            EnforcementSource, name="enforcement_source", native_enum=False
        ),
        nullable=False,
        index=True,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    decision: Mapped[EnforcementDecisionType] = mapped_column(
        SQLEnum(
            EnforcementDecisionType,
            name="enforcement_decision_type",
            native_enum=False,
        ),
        nullable=False,
        index=True,
    )
    reason_codes: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    estimated_monthly_delta_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False
    )
    estimated_hourly_delta_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    allocation_available_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    credits_available_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    reserved_allocation_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    reserved_credit_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    reservation_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_token_issued: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )


class EnforcementDecisionLedger(Base):
    __tablename__ = "enforcement_decision_ledger"
    __table_args__ = (
        Index(
            "ix_enforcement_decision_ledger_tenant_recorded",
            "tenant_id",
            "recorded_at",
        ),
        Index(
            "ix_enforcement_decision_ledger_decision",
            "decision_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("enforcement_decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[EnforcementSource] = mapped_column(
        SQLEnum(
            EnforcementSource,
            name="enforcement_source",
            native_enum=False,
        ),
        nullable=False,
        index=True,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    decision: Mapped[EnforcementDecisionType] = mapped_column(
        SQLEnum(
            EnforcementDecisionType,
            name="enforcement_decision_type",
            native_enum=False,
        ),
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    estimated_monthly_delta_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
    )
    estimated_hourly_delta_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
    )
    reserved_total_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        default=Decimal("0"),
    )
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    request_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    decision_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )


class EnforcementApprovalRequest(Base):
    __tablename__ = "enforcement_approval_requests"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_enforcement_approval_decision"),
        Index("ix_enforcement_approval_status_expires", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("enforcement_decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[EnforcementApprovalStatus] = mapped_column(
        SQLEnum(
            EnforcementApprovalStatus,
            name="enforcement_approval_status",
            native_enum=False,
        ),
        nullable=False,
        default=EnforcementApprovalStatus.PENDING,
        index=True,
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    approval_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_token_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


@event.listens_for(EnforcementDecisionLedger, "before_update")
def _enforcement_decision_ledger_prevent_update(*_: object) -> None:
    raise ValueError("EnforcementDecisionLedger is append-only and immutable.")


@event.listens_for(EnforcementDecisionLedger, "before_delete")
def _enforcement_decision_ledger_prevent_delete(*_: object) -> None:
    raise ValueError("EnforcementDecisionLedger is append-only and immutable.")
