"""
Remediation Request Model

Stores pending remediation requests that require human approval.
Implements a full audit trail for compliance and safety.

Workflow:
1. User scans for zombies → sees resources
2. User requests remediation → creates pending request
3. Reviewer approves/rejects → updates status
4. On approval → system executes action (with optional backup)
5. All actions logged for audit
"""

from uuid import uuid4, UUID
from enum import Enum
from decimal import Decimal
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, Enum as SQLEnum, Numeric, Index, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.shared.db.base import Base


class RemediationStatus(str, Enum):
    """Status of a remediation request."""
    PENDING = "pending"           # Awaiting approval
    APPROVED = "approved"         # Approved, ready to execute
    EXECUTING = "executing"       # Currently being executed
    SCHEDULED = "scheduled"       # Scheduled for future execution (grace period)
    COMPLETED = "completed"       # Successfully executed
    FAILED = "failed"             # Execution failed
    REJECTED = "rejected"         # Human rejected the request
    CANCELLED = "cancelled"       # User cancelled before approval


class RemediationAction(str, Enum):
    """Types of remediation actions."""
    DELETE_VOLUME = "delete_volume"
    DELETE_SNAPSHOT = "delete_snapshot"
    RELEASE_ELASTIC_IP = "release_elastic_ip"
    STOP_INSTANCE = "stop_instance"
    TERMINATE_INSTANCE = "terminate_instance"
    DELETE_S3_BUCKET = "delete_s3_bucket"
    DELETE_ECR_IMAGE = "delete_ecr_image"
    DELETE_SAGEMAKER_ENDPOINT = "delete_sagemaker_endpoint"
    DELETE_REDSHIFT_CLUSTER = "delete_redshift_cluster"
    DELETE_LOAD_BALANCER = "delete_load_balancer"
    STOP_RDS_INSTANCE = "stop_rds_instance"
    DELETE_RDS_INSTANCE = "delete_rds_instance"
    DELETE_NAT_GATEWAY = "delete_nat_gateway"
    RESIZE_INSTANCE = "resize_instance"
    MANUAL_REVIEW = "manual_review"


class RemediationRequest(Base):
    """
    A request to remediate (delete/modify) a zombie resource.

    Requires human approval before execution.
    Supports optional backup before destructive actions.
    """

    __tablename__ = "remediation_requests"
    __table_args__ = (
        Index('ix_remediation_tenant_resource', 'tenant_id', 'resource_id'),
    )

    # Primary Key
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Multi-tenancy
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Resource identification
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="aws") # aws, azure, gcp
    connection_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)     # ID of the specific cloud connection
    region: Mapped[str] = mapped_column(String(20), nullable=False, default="us-east-1")

    # Action details
    action: Mapped[RemediationAction] = mapped_column(SQLEnum(RemediationAction), nullable=False)
    status: Mapped[RemediationStatus] = mapped_column(
        SQLEnum(RemediationStatus),
        nullable=False,
        default=RemediationStatus.PENDING,
        index=True,
    )

    # Financial impact
    estimated_monthly_savings: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # AI Explainability
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), nullable=True) # 0.00 to 1.00
    explainability_notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True) # AI Reasoning

    # Backup options (for safe delete)
    create_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    backup_resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ID of created backup
    backup_cost_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)  # Monthly cost of backup

    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    # Audit trail - who approved/rejected
    reviewed_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    review_notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Execution details
    execution_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    scheduled_execution_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])

    def __repr__(self) -> str:
        return f"<RemediationRequest {self.resource_id} [{self.status.value}]>"
