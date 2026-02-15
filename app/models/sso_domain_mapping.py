"""
SSO Domain Mappings (Public Routing)

Why this exists:
- `tenant_identity_settings` is tenant-scoped and protected by Postgres RLS, so a public
  "discover SSO by email domain" endpoint cannot query it safely without a tenant context.
- We still need a way to route a login attempt to the correct IdP bootstrap parameters.

This table is intentionally minimal and non-secret:
- domain -> tenant_id + federation_mode/provider_id

It must never store bearer tokens or SCIM secrets.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class SsoDomainMapping(Base):
    __tablename__ = "sso_domain_mappings"
    __table_args__ = (UniqueConstraint("domain", name="uq_sso_domain_mappings_domain"),)

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

    # Lowercased, normalized email domain (for example: example.com).
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # domain | provider_id (Supabase signInWithSSO bootstrap mode).
    federation_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="domain"
    )
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
