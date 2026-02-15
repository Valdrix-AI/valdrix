from uuid import UUID, uuid4
from enum import Enum
from datetime import datetime
from typing import Any, Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    String,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    event,
    Uuid as PG_UUID,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base
from app.shared.core.security import generate_blind_index

from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
from app.shared.core.config import get_settings

if TYPE_CHECKING:
    from app.models.llm import LLMUsage, LLMBudget
    from app.models.aws_connection import AWSConnection
    from app.models.saas_connection import SaaSConnection
    from app.models.license_connection import LicenseConnection
    from app.models.platform_connection import PlatformConnection
    from app.models.hybrid_connection import HybridConnection
    from app.models.notification_settings import NotificationSettings
    from app.models.background_job import BackgroundJob

settings = get_settings()
_encryption_key = settings.ENCRYPTION_KEY

if not _encryption_key:
    # Fail-fast at import time to prevent accidental plaintext storage
    raise RuntimeError("ENCRYPTION_KEY not set. Cannot start securely.")


class UserRole(str, Enum):
    """RBAC Role Definitions."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class UserPersona(str, Enum):
    """
    Product persona preference (UX default), not a permission boundary.

    Permissions remain enforced by RBAC + tier checks. Persona only influences the
    default UI/navigation and which widgets are loaded first.
    """

    ENGINEERING = "engineering"
    FINANCE = "finance"
    PLATFORM = "platform"
    LEADERSHIP = "leadership"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"), index=True
    )
    name_bidx: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    plan: Mapped[str] = mapped_column(
        String, default="free_trial"
    )  # Updated to use PricingTier in logic
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Trial tracking
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Activity tracking (Phase 7: Lazy Tenant Pattern)
    # Updated on dashboard access for dormancy detection
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    users: Mapped[List["User"]] = relationship(
        back_populates="tenant", cascade="all, delete"
    )
    llm_usage: Mapped[List["LLMUsage"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    llm_budget: Mapped[Optional["LLMBudget"]] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    aws_connections: Mapped[List["AWSConnection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    saas_connections: Mapped[List["SaaSConnection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    license_connections: Mapped[List["LicenseConnection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    platform_connections: Mapped[List["PlatformConnection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    hybrid_connections: Mapped[List["HybridConnection"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    notification_settings: Mapped[Optional["NotificationSettings"]] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    background_jobs: Mapped[List["BackgroundJob"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_bidx", name="uq_tenant_user_email"),
    )

    # We use the Supabase User ID (which is a UUID) as our PK
    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"), index=True
    )
    email_bidx: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String, default="member")
    persona: Mapped[str] = mapped_column(String, default=UserPersona.ENGINEERING.value)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


# SQLAlchemy Listeners to keep Blind Indexes in sync
@event.listens_for(Tenant.name, "set")
def on_tenant_name_set(target: Tenant, value: str, _old: str, _init: Any) -> None:
    target.name_bidx = generate_blind_index(value)


@event.listens_for(User.email, "set")
def on_user_email_set(target: User, value: str, _old: str, _init: Any) -> None:
    target.email_bidx = generate_blind_index(value)
