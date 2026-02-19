from uuid import UUID, uuid4
from sqlalchemy import Boolean, Numeric, Integer, ForeignKey, String, Uuid as SAUuid

# from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class RemediationSettings(Base):
    """
    Per-tenant settings for Autonomous Remediation (ActiveOps).
    """

    __tablename__ = "remediation_settings"

    id: Mapped[UUID] = mapped_column(SAUuid(), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        SAUuid(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Global Kill-Switch for Auto-Pilot
    auto_pilot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Safety Thresholds
    min_confidence_threshold: Mapped[float] = mapped_column(Numeric(3, 2), default=0.95)

    # Rate Limiting Safety Fuse
    max_deletions_per_hour: Mapped[int] = mapped_column(Integer, default=10)

    # Simulation Mode - dry-run preview without actual execution
    simulation_mode: Mapped[bool] = mapped_column(Boolean, default=True)

    # Cloud Hard Caps (Phase 36)
    hard_cap_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_hard_cap_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    # Policy Guardrail Controls (tier-gated via API)
    policy_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_block_production_destructive: Mapped[bool] = mapped_column(
        Boolean, default=True
    )
    policy_require_gpu_override: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_low_confidence_warn_threshold: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.90
    )
    policy_violation_notify_slack: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_violation_notify_jira: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_escalation_required_role: Mapped[str] = mapped_column(
        String(20), default="owner"
    )

    # Autonomous License Governance (Phase 8)
    license_auto_reclaim_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    license_inactive_threshold_days: Mapped[int] = mapped_column(
        Integer, default=30
    )
    license_reclaim_grace_period_days: Mapped[int] = mapped_column(
        Integer, default=3
    )
    license_downgrade_recommendations_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    # Relationship
    tenant: Mapped["Tenant"] = relationship("Tenant")

    def __repr__(self) -> str:
        return f"<RemediationSettings tenant={self.tenant_id} auto_pilot={self.auto_pilot_enabled}>"
