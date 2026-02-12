from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, TYPE_CHECKING
from uuid import uuid4, UUID
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, JSON, ForeignKey, DateTime, Uuid as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant

class CommitmentTerm(str, Enum):
    ONE_YEAR = "1_year"
    THREE_YEAR = "3_year"

class PaymentOption(str, Enum):
    NO_UPFRONT = "no_upfront"
    PARTIAL_UPFRONT = "partial_upfront"
    ALL_UPFRONT = "all_upfront"

class StrategyType(str, Enum):
    RI = "reserved_instance"
    SAVINGS_PLAN = "savings_plan"
    SPOT = "spot_instance"
    RIGHTSIZING = "rightsizing"

class OptimizationStrategy(Base):
    """
    Configuration for an optimization strategy available to a tenant.
    """
    __tablename__ = "optimization_strategies"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    type: Mapped[StrategyType] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # aws, azure, gcp
    
    # Configuration for the strategy (e.g., min_savings_threshold, excluded_regions)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )

class StrategyRecommendation(Base):
    """
    Specific recommendation generated for a tenant based on a strategy.
    """
    __tablename__ = "strategy_recommendations"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(), 
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("optimization_strategies.id"),
        nullable=False
    )
    
    # Details of the recommendation
    resource_type: Mapped[str] = mapped_column(String(100)) # e.g., "m5.large", "compute-sp"
    region: Mapped[str] = mapped_column(String(50))
    term: Mapped[CommitmentTerm] = mapped_column(String(20))
    payment_option: Mapped[PaymentOption] = mapped_column(String(20))
    
    # Financial Impact
    upfront_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.0)
    monthly_recurring_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.0)
    estimated_monthly_savings_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated_monthly_savings_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    roi_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # e.g., 25.5 for 25.5%
    break_even_months: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="open") # open, applied, dismissed
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    strategy: Mapped["OptimizationStrategy"] = relationship("OptimizationStrategy")
    tenant: Mapped["Tenant"] = relationship("Tenant") # Assuming Tenant model exists and is importable via string
