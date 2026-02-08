"""
Anomaly Marker Model for Forecast Tuning

Allows customers to mark known anomalies (Black Friday, batch jobs, holidays)
so the forecasting engine can exclude or weight them appropriately.

Phase 3.2: Manual intervention markers for forecast tuning.
"""

from datetime import date, datetime, timezone

from uuid import UUID, uuid4
from sqlalchemy import String, Text, ForeignKey, Date, DateTime, Boolean, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base


class AnomalyMarker(Base):
    """
    Customer-defined anomaly markers for forecast tuning.
    
    Allows marking specific dates as expected anomalies to improve forecast accuracy.
    """
    __tablename__ = "anomaly_markers"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # The date(s) marked as anomalous
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Type of anomaly for forecast handling
    marker_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        default="EXPECTED_SPIKE"
    )  # EXPECTED_SPIKE, EXPECTED_DROP, HOLIDAY, BATCH_JOB, MAINTENANCE
    
    # Human-readable label
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Service filter (optional - if empty, applies to all services)
    service_filter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Forecast behavior
    exclude_from_training: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Audit
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    
    def __repr__(self) -> str:
        return f"<AnomalyMarker {self.label} ({self.start_date} - {self.end_date})>"
