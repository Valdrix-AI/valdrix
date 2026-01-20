import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Date, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class CostAuditLog(Base):
    """
    Forensic audit trail for cost restatements.
    Tracks changes to cost records when AWS/Azure/GCP restate their bills.
    """
    __tablename__ = "cost_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cost_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cost_recorded_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    old_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    new_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    
    # Contextual information
    reason: Mapped[str] = mapped_column(String, default="RESTATEMENT") # e.g., AWS_RESTATEMENT, RE-INGESTION
    ingestion_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship
    cost_record = relationship("CostRecord")

    __table_args__ = (
        ForeignKeyConstraint(
            ["cost_record_id", "cost_recorded_at"],
            ["cost_records.id", "cost_records.recorded_at"],
            name="fk_cost_audit_logs_cost_record"
        ),
    )
