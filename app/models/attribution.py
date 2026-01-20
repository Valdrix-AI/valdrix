import uuid
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import String, ForeignKey, JSON, Integer, Numeric, DateTime, Date, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.cloud import CostRecord

class AttributionRule(Base):
    """
    Enterprise Allocation Rules for cost attribution.
    Allows splitting shared costs or overriding tag-based grouping.
    """
    __tablename__ = "attribution_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    
    # PERCENTAGE (split), DIRECT (one bucket), FIXED (specific amount)
    rule_type: Mapped[str] = mapped_column(String, default="DIRECT") 
    
    # Conditions: e.g., {"service": "AmazonS3", "tags": {"Environment": "Prod"}}
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Allocation Targets: e.g., [{"bucket": "Marketing", "percentage": 30}, {"bucket": "Sales", "percentage": 70}]
    allocation: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship()
    cost_records: Mapped[List["CostRecord"]] = relationship(back_populates="attribution_rule")
    allocations: Mapped[List["CostAllocation"]] = relationship(back_populates="rule")

class CostAllocation(Base):
    """
    Sub-record table for cost splits.
    Allows one CostRecord to be split across multiple allocation buckets.
    """
    __tablename__ = "cost_allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cost_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    recorded_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attribution_rules.id"), nullable=True)
    
    allocated_to: Mapped[str] = mapped_column(String, nullable=False, index=True) # Bucket Name
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True) # e.g. 30.00
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Relationships
    rule: Mapped["AttributionRule | None"] = relationship(back_populates="allocations")

    __table_args__ = (
        ForeignKeyConstraint(
            ["cost_record_id", "recorded_at"],
            ["cost_records.id", "cost_records.recorded_at"],
            name="fk_cost_allocations_cost_record"
        ),
    )
