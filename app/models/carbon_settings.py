"""
Carbon Settings Model

Stores per-tenant carbon budget configuration.
"""

from uuid import UUID, uuid4
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from app.shared.db.base import Base
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
from app.shared.core.config import get_settings

if TYPE_CHECKING:
    from app.models.tenant import Tenant

settings = get_settings()
_encryption_key = settings.ENCRYPTION_KEY


class CarbonSettings(Base):
    """
    Carbon budget settings for a tenant.

    Configurable values:
    - carbon_budget_kg: Monthly CO2 limit in kg
    - alert_threshold_percent: Percentage at which to send warning
    - default_region: Default AWS region for carbon intensity
    - email_enabled: Whether to send email notifications
    - email_recipients: Comma-separated list of email addresses
    """
    __tablename__ = "carbon_settings"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), unique=True, nullable=False)

    # Budget configuration
    carbon_budget_kg: Mapped[float] = mapped_column(Float, default=100.0)  # kg CO2/month
    alert_threshold_percent: Mapped[int] = mapped_column(Integer, default=80)  # % before warning

    # Region configuration
    default_region: Mapped[str] = mapped_column(String, default="us-east-1")

    # Email notification settings
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_recipients: Mapped[str | None] = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"),
        nullable=True
    )  # Comma-separated

    # Alert rate limiting
    last_alert_sent: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship
    tenant: Mapped["Tenant"] = relationship("Tenant", backref="carbon_settings")
