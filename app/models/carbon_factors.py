"""
Carbon Factor Sets (Audit-Grade)

Enterprise carbon reporting needs reproducibility:
- factors must be versioned
- changes must be auditable
- calculations must reference the active factor set used at the time

Valdrics stores carbon factors as a first-class, DB-backed artifact so updates can be staged,
guardrailed, and activated without a code deploy.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import User


class CarbonFactorSet(Base):
    """
    Versioned carbon factor set.

    One factor set is active at a time. New factor sets are staged and activated after guardrails pass.
    """

    __tablename__ = "carbon_factor_sets"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)

    # Status lifecycle: staged -> active -> archived | blocked
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="staged", index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    factor_source: Mapped[str] = mapped_column(String(255), nullable=False)
    factor_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    factor_timestamp: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)

    factors_checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user: Mapped["User | None"] = relationship("User")


class CarbonFactorUpdateLog(Base):
    """
    Global audit log for factor-set activations/blocks.

    This is intentionally NOT tenant-scoped; factor sets are global and do not contain tenant data.
    """

    __tablename__ = "carbon_factor_update_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    old_factor_set_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(), nullable=True, index=True
    )
    new_factor_set_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(), nullable=True, index=True
    )
    old_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user: Mapped["User | None"] = relationship("User")
