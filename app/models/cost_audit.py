from uuid import UUID, uuid4
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    Date,
    ForeignKeyConstraint,
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

    # Relationship
    cost_record: Mapped["CostRecord"] = relationship("CostRecord")

    __table_args__ = (
        ForeignKeyConstraint(
            ["cost_record_id", "cost_recorded_at"],
            ["cost_records.id", "cost_records.recorded_at"],
            name="fk_cost_audit_logs_cost_record",
        ),
    )
