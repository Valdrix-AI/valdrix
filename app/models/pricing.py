from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, DateTime, Numeric, Boolean, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base

class PricingPlan(Base):
    """
    Database-driven pricing plans. 
    Allows updating prices and features without code deployment.
    """
    __tablename__ = "pricing_plans"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. 'starter', 'growth'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    price_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Store features and limits as JSONB for flexibility
    features: Mapped[Dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    limits: Mapped[Dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    
    # UI Metadata
    display_features: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=list)
    cta_text: Mapped[str] = mapped_column(String(50), default="Get Started")
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Timestamps are inherited from Base

class ExchangeRate(Base):
    """
    Stores exchange rates for currency conversion (e.g., USD to NGN).
    """
    __tablename__ = "exchange_rates"

    from_currency: Mapped[str] = mapped_column(String(3), primary_key=True, default="USD")
    to_currency: Mapped[str] = mapped_column(String(3), primary_key=True, default="NGN")
    
    rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="exchangerate-api")
    
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
