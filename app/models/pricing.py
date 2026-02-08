from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional, Dict, Any
from sqlalchemy import String, DateTime, Numeric, Boolean, JSON, ForeignKey, Uuid as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base

class PricingPlan(Base):
    """
    Database-driven pricing plans. 
    Allows updating prices and features without code deployment.
    """
    __tablename__ = "pricing_plans"
    __table_args__ = {'extend_existing': True}

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
    __table_args__ = {'extend_existing': True}

    from_currency: Mapped[str] = mapped_column(String(3), primary_key=True, default="USD")
    to_currency: Mapped[str] = mapped_column(String(3), primary_key=True, default="NGN")
    
    rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="exchangerate-api")
    
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

class TenantSubscription(Base):
    """
    Formalized subscription record for Paystack integration.
    Aligns with remediate_billing_table.py manual schema.
    """
    __tablename__ = "tenant_subscriptions"
    __table_args__ = {'extend_existing': True}

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(), ForeignKey("tenants.id"), nullable=False, unique=True)
    
    paystack_customer_code: Mapped[Optional[str]] = mapped_column(String(255))
    paystack_subscription_code: Mapped[Optional[str]] = mapped_column(String(255))
    paystack_email_token: Mapped[Optional[str]] = mapped_column(String(255))
    
    tier: Mapped[str] = mapped_column(String(20), default="trial")
    status: Mapped[str] = mapped_column(String(20), default="active")
    
    next_payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Timestamps inherited from Base
