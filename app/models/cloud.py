import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, ForeignKey, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from typing import TYPE_CHECKING
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)

    provider: Mapped[str] = mapped_column(String)  # 'aws', 'azure', 'gcp'
    name: Mapped[str] = mapped_column(String)      # e.g., "Production AWS"

    # Store encrypted JSON blob of credentials (IAM Role ARN, Service Account Key, etc.)
    credentials_encrypted: Mapped[str] = mapped_column(String)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship()
    cost_records: Mapped[list["CostRecord"]] = relationship(back_populates="account")


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cloud_accounts.id"), nullable=False)

    service: Mapped[str] = mapped_column(String, index=True) # e.g., "AmazonEC2"
    region: Mapped[str] = mapped_column(String, nullable=True)
    usage_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Financials (DECIMAL for money!)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    amount_raw: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")

    # GreenOps
    carbon_kg: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    recorded_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    account: Mapped["CloudAccount"] = relationship(back_populates="cost_records")

    __table_args__ = (
        UniqueConstraint('account_id', 'timestamp', 'service', 'region', 'usage_type', name='uix_account_cost_granularity'),
    )
