from datetime import datetime, timezone

from uuid import UUID, uuid4
from typing import TYPE_CHECKING
from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    DateTime,
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



class AzureConnection(Base):
    """
    Represents a tenant's connection to Azure via Service Principal.

    Security:
    - client_id/tenant_id are public
    - client_secret is encrypted at rest (AES-256)
    """

    __tablename__ = "azure_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "subscription_id", name="uq_tenant_azure_subscription"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Connection Name (e.g. "Dev Subscription")
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Azure Service Principal Credentials
    azure_tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    subscription_id: Mapped[str] = mapped_column(String, nullable=False)

    # Secret (Optional for Workload Identity)
    client_secret: Mapped[str | None] = mapped_column(
        StringEncryptedType(String, get_encryption_key, AesEngine, "pkcs5"), nullable=True
    )

    # SEC-HAR-12: Explicit Production Flag (Finding #1-Remediation)
    is_production: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )

    # Auth Method: "secret" or "workload_identity"
    auth_method: Mapped[str] = mapped_column(
        String, default="secret", server_default="secret"
    )

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
    tenant: Mapped["Tenant"] = relationship("Tenant", backref="azure_connections")

    @property
    def provider(self) -> str:
        return "azure"
