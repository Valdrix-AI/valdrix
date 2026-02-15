"""
Realized Savings Evidence Model

Stores finance-grade realized savings evidence derived from post-action billing deltas.

Notes:
- This is intentionally *not* a recommendation model. It is evidence computed from the cost ledger.
- v1 focuses on remediation-driven actions (delete/terminate/stop/etc). Strategy-based realized savings
  can be layered in later.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    JSON,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class RealizedSavingsEvent(Base):
    __tablename__ = "realized_savings_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "remediation_request_id",
            name="uix_realized_savings_tenant_remediation",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    remediation_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("remediation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(length=20), nullable=False, index=True)
    account_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(), nullable=True, index=True
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(length=255), nullable=True, index=True
    )
    service: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)

    method: Mapped[str] = mapped_column(
        String(length=64), nullable=False, default="ledger_delta_avg_daily_v1"
    )
    baseline_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    measurement_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    measurement_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    baseline_total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    baseline_observed_days: Mapped[int] = mapped_column(nullable=False, default=0)
    measurement_total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    measurement_observed_days: Mapped[int] = mapped_column(nullable=False, default=0)

    baseline_avg_daily_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    measurement_avg_daily_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    realized_avg_daily_savings_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    realized_monthly_savings_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    monthly_multiplier_days: Mapped[int] = mapped_column(nullable=False, default=30)

    confidence_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
