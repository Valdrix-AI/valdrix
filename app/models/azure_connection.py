from datetime import datetime
import uuid
from sqlalchemy import String, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

from app.db.base import Base
from app.core.config import get_settings

settings = get_settings()
_encryption_key = settings.ENCRYPTION_KEY

class AzureConnection(Base):
    """
    Represents a tenant's connection to Azure via Service Principal.
    
    Security:
    - client_id/tenant_id are public
    - client_secret is encrypted at rest (AES-256)
    """
    __tablename__ = "azure_connections"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'subscription_id', name='uq_tenant_azure_subscription'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Connection Name (e.g. "Dev Subscription")
    name: Mapped[str] = mapped_column(String, nullable=False)
    
    # Azure Service Principal Credentials
    azure_tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    subscription_id: Mapped[str] = mapped_column(String, nullable=False)
    
    # Secret (Optional for Workload Identity)
    client_secret = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"),
        nullable=True
    )

    # Auth Method: "secret" or "workload_identity"
    auth_method: Mapped[str] = mapped_column(String, default="secret", server_default="secret")
    
    # Status tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", backref="azure_connections")

    @property
    def provider(self) -> str:
        return "azure"
