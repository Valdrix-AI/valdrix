from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid as PG_UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

from app.models._encryption import get_encryption_key
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant



class SaaSConnection(Base):
    """
    Cloud+ connector for SaaS vendor spend feeds.

    The feed payload is intentionally generic so teams can onboard vendor APIs,
    CSV imports, or manual exports without schema churn.
    """

    __tablename__ = "saas_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "vendor", "name", name="uq_tenant_saas_vendor_name"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    auth_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default="manual"
    )
    api_key: Mapped[str | None] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )
    connector_config: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    spend_feed: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="saas_connections")

    @property
    def provider(self) -> str:
        return "saas"

    @property
    def cost_feed(self) -> list[dict[str, Any]]:
        return self.spend_feed
