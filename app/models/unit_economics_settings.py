from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class UnitEconomicsSettings(Base):
    """
    Per-tenant defaults for unit-economics KPIs.
    These denominators are used to compute cost per request/workload/customer.
    """

    __tablename__ = "unit_economics_settings"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    default_request_volume: Mapped[float] = mapped_column(
        Numeric(18, 4), default=1000.0
    )
    default_workload_volume: Mapped[float] = mapped_column(
        Numeric(18, 4), default=100.0
    )
    default_customer_volume: Mapped[float] = mapped_column(Numeric(18, 4), default=50.0)
    anomaly_threshold_percent: Mapped[float] = mapped_column(
        Numeric(8, 2), default=20.0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant")
