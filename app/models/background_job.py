"""
Background Job SQLAlchemy Model

Represents jobs in the background_jobs table for durable job processing.
"""

from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Boolean,
    event,
    JSON,
    Uuid as PG_UUID,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class JobStatus(str, Enum):
    """Job lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"  # Max attempts exceeded


class JobType(str, Enum):
    """Supported background job types."""

    FINOPS_ANALYSIS = "finops_analysis"
    ZOMBIE_SCAN = "zombie_scan"
    REMEDIATION = "remediation"
    ACCEPTANCE_SUITE_CAPTURE = "acceptance_suite_capture"
    WEBHOOK_RETRY = "webhook_retry"
    REPORT_GENERATION = "report_generation"
    NOTIFICATION = "notification"
    COST_INGESTION = "cost_ingestion"
    COST_ANOMALY_DETECTION = "cost_anomaly_detection"
    RECURRING_BILLING = "recurring_billing"
    ZOMBIE_ANALYSIS = "zombie_analysis"
    COST_FORECAST = "cost_forecast"
    COST_EXPORT = "cost_export"  # Phase 4.2: Async export for >10M records
    COST_AGGREGATION = (
        "cost_aggregation"  # Phase 4.2: Async aggregation for large datasets
    )
    DUNNING = "dunning"  # Payment retry and customer notifications


class BackgroundJob(Base):
    """
    Durable background job stored in PostgreSQL.

    Processed by pg_cron scheduler for reliability:
    - Survives app restarts
    - Automatic retries with backoff
    - Full audit trail
    """

    __tablename__ = "background_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # BE-SCHED-6: Deduplication key for idempotent enqueuing (tenant_id:job_type:bucket)
    deduplication_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING, index=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    # BE-SCHED-5: Job priority (higher = more urgent, 0 = normal, negative = low priority)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="background_jobs")

    def __repr__(self) -> str:
        return f"<BackgroundJob {self.id} type={self.job_type} status={self.status}>"


# Item P3: Audit Trigger for deletions
@event.listens_for(BackgroundJob, "before_delete")
def audit_job_deletion(_mapper: Any, _connection: Any, target: BackgroundJob) -> None:
    """
    Log job deletion to audit trail before it's gone.
    """
    import structlog

    audit_logger = structlog.get_logger("audit.deletion")
    audit_logger.info(
        "resource_permanently_deleted",
        resource_type="background_job",
        resource_id=str(target.id),
        tenant_id=str(target.tenant_id),
        job_type=str(target.job_type),
    )
