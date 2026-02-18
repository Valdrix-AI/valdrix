"""
Tenant Identity Settings

Stores tenant-scoped SSO enforcement primitives and SCIM provisioning tokens.

Design notes:
- SCIM bearer tokens are encrypted at rest.
- We also store a deterministic blind index for token lookup without decrypting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    String,
    event,
    func,
    text,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

from app.models._encryption import get_encryption_key
from app.shared.core.security import generate_secret_blind_index
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant




class TenantIdentitySettings(Base):
    """Identity policy and SCIM provisioning settings for a tenant."""

    __tablename__ = "tenant_identity_settings"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # "SSO enabled" here is enforced as domain allowlisting at the API layer.
    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_email_domains: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    # Real SSO federation bootstrap (Supabase SSO):
    # - domain mode: signInWithSSO({ domain: user_email_domain })
    # - provider_id mode: signInWithSSO({ providerId: configured_provider_id })
    sso_federation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sso_federation_mode: Mapped[str] = mapped_column(
        String(32), default="domain", nullable=False
    )
    sso_federation_provider_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # SCIM provisioning (Enterprise feature)
    scim_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scim_bearer_token: Mapped[str | None] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )
    scim_token_bidx: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    scim_last_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scim_group_mappings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
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

    tenant: Mapped["Tenant"] = relationship("Tenant")

    def __repr__(self) -> str:
        return f"<TenantIdentitySettings tenant={self.tenant_id} sso={self.sso_enabled} scim={self.scim_enabled}>"


@event.listens_for(TenantIdentitySettings.scim_bearer_token, "set")
def _on_scim_token_set(
    target: TenantIdentitySettings, value: str | None, _old: str | None, _init: object
) -> None:
    target.scim_token_bidx = generate_secret_blind_index(value) if value else None
