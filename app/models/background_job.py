"""
Background Job SQLAlchemy Model

Represents jobs in the background_jobs table for durable job processing.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base

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
    WEBHOOK_RETRY = "webhook_retry"
    REPORT_GENERATION = "report_generation"
    NOTIFICATION = "notification"
    COST_INGESTION = "cost_ingestion"


class BackgroundJob(Base):
    """
    Durable background job stored in PostgreSQL.
    
    Processed by pg_cron scheduler for reliability:
    - Survives app restarts
    - Automatic retries with backoff
    - Full audit trail
    """
    __tablename__ = "background_jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), 
        nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="background_jobs")
    
    def __repr__(self) -> str:
        return f"<BackgroundJob {self.id} type={self.job_type} status={self.status}>"
