from uuid import UUID, uuid4
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    Date,
    Index,
    Uuid as PG_UUID,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.cloud import CostRecord


class CostAuditLog(Base):
    """
    Forensic audit trail for cost restatements.
    Tracks changes to cost records when AWS/Azure/GCP restate their bills.
    """

    __tablename__ = "cost_audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    cost_record_id: Mapped[UUID] = mapped_column(PG_UUID(), nullable=False, index=True)
    cost_recorded_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    old_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    new_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    # Contextual information
    reason: Mapped[str] = mapped_column(
        String, default="RESTATEMENT"
    )  # e.g., AWS_RESTATEMENT, RE-INGESTION
    ingestion_batch_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(), nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship – DB-level FK was dropped (migration 53d52a0a90e0) because
    # cost_records is range-partitioned on recorded_at.  We supply an explicit
    # string-based primaryjoin so SQLAlchemy can resolve the join lazily.
    cost_record: Mapped["CostRecord"] = relationship(
        "CostRecord",
        primaryjoin="and_(CostAuditLog.cost_record_id == CostRecord.id, "
        "CostAuditLog.cost_recorded_at == CostRecord.recorded_at)",
        foreign_keys="[CostAuditLog.cost_record_id, CostAuditLog.cost_recorded_at]",
        viewonly=True,
        lazy="select",
    )

    __table_args__ = (
        Index("ix_cost_audit_logs_composite_record", "cost_record_id", "cost_recorded_at"),
    )
