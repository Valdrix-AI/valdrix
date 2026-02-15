"""
SCIM Group Models

These tables exist to support SCIM Group push from IdPs that manage membership
via /Groups (instead of embedding groups in the /Users payload).

Design:
- Tenant-scoped (multi-tenant safe).
- `display_name_norm` is used for deterministic mapping and case-insensitive lookup.
- Membership is stored so we can recompute user entitlements when group membership changes.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
    Uuid as PG_UUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class ScimGroup(Base):
    __tablename__ = "scim_groups"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "display_name_norm",
            name="uq_scim_group_tenant_display_name_norm",
        ),
        UniqueConstraint(
            "tenant_id",
            "external_id_norm",
            name="uq_scim_group_tenant_external_id_norm",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    display_name_norm: Mapped[str] = mapped_column(
        String(length=255), nullable=False, index=True
    )

    external_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    external_id_norm: Mapped[str | None] = mapped_column(
        String(length=255), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ScimGroup id={self.id} tenant={self.tenant_id} name={self.display_name_norm}>"


class ScimGroupMember(Base):
    __tablename__ = "scim_group_members"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "group_id",
            "user_id",
            name="uq_scim_group_member_tenant_group_user",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("scim_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<ScimGroupMember tenant={self.tenant_id} group={self.group_id} user={self.user_id}>"
