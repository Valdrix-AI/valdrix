from uuid import UUID, uuid4
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import String, ForeignKey, JSON, Integer, Numeric, DateTime, Date, ForeignKeyConstraint, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.cloud import CostRecord

class AttributionRule(Base):
    """
    Enterprise Allocation Rules for cost attribution.
    Allows splitting shared costs or overriding tag-based grouping.
    """
    __tablename__ = "attribution_rules"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    
    # PERCENTAGE (split), DIRECT (one bucket), FIXED (specific amount)
    rule_type: Mapped[str] = mapped_column(String, default="DIRECT") 
    
    # Conditions: e.g., {"service": "AmazonS3", "tags": {"Environment": "Prod"}}
    conditions: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    
    # Allocation Targets: e.g., [{"bucket": "Marketing", "percentage": 30}, {"bucket": "Sales", "percentage": 70}]
    allocation: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    
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

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    cost_record_id: Mapped[UUID] = mapped_column(PG_UUID(), nullable=False, index=True)
    recorded_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    rule_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("attribution_rules.id"), nullable=True)
    
    allocated_to: Mapped[str] = mapped_column(String, nullable=False, index=True) # Bucket Name
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True) # e.g. 30.00
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Relationships
    rule: Mapped[Optional["AttributionRule"]] = relationship(back_populates="allocations")

    __table_args__ = (
        ForeignKeyConstraint(
            ["cost_record_id", "recorded_at"],
            ["cost_records.id", "cost_records.recorded_at"],
            name="fk_cost_allocations_cost_record"
        ),
    )
