from uuid import UUID, uuid4
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, ForeignKey, Numeric, Date, DateTime, UniqueConstraint, JSON, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from typing import TYPE_CHECKING, List, Dict, Any, Optional
from app.shared.db.base import Base, get_partition_args

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.attribution import AttributionRule

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)

    provider: Mapped[str] = mapped_column(String)  # 'aws', 'azure', 'gcp'
    name: Mapped[str] = mapped_column(String)      # e.g., "Production AWS"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship()
    cost_records: Mapped[List["CostRecord"]] = relationship(back_populates="account")


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("cloud_accounts.id"), nullable=False)

    service: Mapped[str] = mapped_column(String, index=True) # e.g., "AmazonEC2"
    region: Mapped[str] = mapped_column(String, nullable=True)
    usage_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Financials (DECIMAL for money!)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    amount_raw: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")

    # GreenOps
    carbon_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)

    # SEC: Cost Reconciliation (BE-COST-1)
    is_preliminary: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    cost_status: Mapped[str] = mapped_column(String, default="PRELIMINARY", index=True) # PRELIMINARY, FINAL
    reconciliation_run_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(), index=True, nullable=True)
    
    # Forensic Lineage (FinOps Audit Phase 1)
    ingestion_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # SEC: Attribution & Allocation (FinOps Audit Phase 2)
    attribution_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("attribution_rules.id", name="fk_cost_records_attribution"),
        nullable=True, 
        index=True
    )
    allocated_to: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True) # Bucket name (Team/Project)

    recorded_at: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False, index=True)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    account: Mapped["CloudAccount"] = relationship(back_populates="cost_records")
    attribution_rule: Mapped[Optional["AttributionRule"]] = relationship(back_populates="cost_records")

    __table_args__ = (
        UniqueConstraint('account_id', 'timestamp', 'service', 'region', 'usage_type', 'recorded_at', name='uix_account_cost_granularity'),
        get_partition_args('RANGE (recorded_at)'),
    )

