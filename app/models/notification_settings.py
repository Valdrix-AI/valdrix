"""
Notification Settings Model for Valdrix.
Stores per-tenant notification preferences.
"""
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, text, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class NotificationSettings(Base):
    """Per-tenant notification preferences."""

    __tablename__ = "notification_settings"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign key to tenant
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,  # One settings record per tenant
        nullable=False,
    )

    # Slack configuration
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slack_channel_override: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Digest schedule: "daily", "weekly", "disabled"
    digest_schedule: Mapped[str] = mapped_column(String(20), default="daily")
    digest_hour: Mapped[int] = mapped_column(default=9)  # 24-hour format, UTC
    digest_minute: Mapped[int] = mapped_column(default=0)

    # Alert preferences
    alert_on_budget_warning: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_carbon_budget_warning: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_carbon_budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_zombie_detected: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps are inherited from Base

    # Relationship
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="notification_settings")

    def __repr__(self) -> str:
        return f"<NotificationSettings tenant={self.tenant_id} schedule={self.digest_schedule}>"
