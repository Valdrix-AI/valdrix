from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    DateTime,
    Numeric,
    Boolean,
    JSON,
    ForeignKey,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class PricingPlan(Base):
    """
    Database-driven pricing plans.
    Allows updating prices and features without code deployment.
    """

    __tablename__ = "pricing_plans"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # e.g. 'starter', 'growth'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    price_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Store features and limits as JSONB for flexibility
    features: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    limits: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )

    # UI Metadata
    display_features: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    cta_text: Mapped[str] = mapped_column(String(50), default="Get Started")
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Timestamps are inherited from Base


class ExchangeRate(Base):
    """
    Stores exchange rates for currency conversion (e.g., USD to NGN).
    """

    __tablename__ = "exchange_rates"
    __table_args__ = {"extend_existing": True}

    from_currency: Mapped[str] = mapped_column(
        String(3), primary_key=True, default="USD"
    )
    to_currency: Mapped[str] = mapped_column(String(3), primary_key=True, default="NGN")

    rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="exchangerate-api")

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TenantSubscription(Base):
    """
    Formalized subscription record for Paystack integration.
    Includes dunning tracking and reusable auth codes.
    """

    __tablename__ = "tenant_subscriptions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Paystack IDs
    paystack_customer_code: Mapped[Optional[str]] = mapped_column(String(255))
    paystack_subscription_code: Mapped[Optional[str]] = mapped_column(String(255))
    paystack_email_token: Mapped[Optional[str]] = mapped_column(String(255))
    paystack_auth_code: Mapped[Optional[str]] = mapped_column(String(255))

    tier: Mapped[str] = mapped_column(String(20), default="free")
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Billing & Dunning
    next_payment_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dunning_attempts: Mapped[int] = mapped_column(Numeric(2, 0), default=0)
    last_dunning_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dunning_next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class LLMProviderPricing(Base):
    """
    Dynamic pricing for LLM providers and models.
    Transition from hardcoded 2026 rates to DB-driven costs.
    """

    __tablename__ = "llm_provider_pricing"
    __table_args__ = {"extend_existing": True}

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(50), index=True)  # groq, openai, etc.
    model: Mapped[str] = mapped_column(String(100), index=True)

    input_cost_per_million: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    output_cost_per_million: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False
    )

    free_tier_tokens: Mapped[int] = mapped_column(Numeric(20, 0), default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
