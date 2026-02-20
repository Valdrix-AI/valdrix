from datetime import datetime, timezone

from uuid import UUID, uuid4
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    UniqueConstraint,
    Uuid as PG_UUID,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant
from app.models._encryption import get_encryption_key



class GCPConnection(Base):
    """
    Represents a tenant's connection to Google Cloud Platform via Service Account.

    Security:
    - project_id is public
    - service_account_json is encrypted at rest (AES-256)
      (Contains private_key, client_email, etc.)
    """

    __tablename__ = "gcp_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", name="uq_tenant_gcp_project"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Connection Name (e.g. "Production Project")
    name: Mapped[str] = mapped_column(String, nullable=False)

    # GCP Identifiers
    project_id: Mapped[str] = mapped_column(String, nullable=False)

    # Encrypted Credentials (Full JSON blob) - Optional for Workload Identity
    service_account_json: Mapped[str | None] = mapped_column(
        StringEncryptedType(Text, get_encryption_key, AesEngine, "pkcs5"), nullable=True
    )

    # SEC-HAR-12: Explicit Production Flag (Finding #1-Remediation)
    is_production: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )

    # Auth Method: "secret" or "workload_identity"
    auth_method: Mapped[str] = mapped_column(
        String, default="secret", server_default="secret"
    )

    # Billing Export Configuration (BigQuery)
    billing_project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    billing_dataset: Mapped[str | None] = mapped_column(String, nullable=True)
    billing_table: Mapped[str | None] = mapped_column(String, nullable=True)

    # Status tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", backref="gcp_connections")

    @property
    def provider(self) -> str:
        return "gcp"
