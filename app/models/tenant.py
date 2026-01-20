import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
from app.core.security import generate_blind_index

from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
from app.core.config import get_settings

settings = get_settings()
_encryption_key = settings.ENCRYPTION_KEY

if not _encryption_key:
    # Fail-fast at import time to prevent accidental plaintext storage
    raise RuntimeError("ENCRYPTION_KEY not set. Cannot start securely.")

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"),
        index=True
    )
    name_bidx: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    plan: Mapped[str] = mapped_column(String, default="trial")  # trial, starter, growth, pro, enterprise
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Trial tracking
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Activity tracking (Phase 7: Lazy Tenant Pattern)
    # Updated on dashboard access for dormancy detection
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete")
    llm_usage = relationship("LLMUsage", back_populates="tenant", cascade="all, delete-orphan")
    llm_budget = relationship("LLMBudget", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    aws_connections = relationship("AWSConnection", back_populates="tenant", cascade="all, delete-orphan")
    notification_settings = relationship("NotificationSettings", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    background_jobs = relationship("BackgroundJob", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'email_bidx', name='uq_tenant_user_email'),
    )

    # We use the Supabase User ID (which is a UUID) as our PK
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email = mapped_column(
        StringEncryptedType(String, _encryption_key, AesEngine, "pkcs5"),
        index=True
    )
    email_bidx: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String, default="member") # owner, admin, member


    tenant: Mapped["Tenant"] = relationship(back_populates="users")

# SQLAlchemy Listeners to keep Blind Indexes in sync
@event.listens_for(Tenant.name, "set")
def on_tenant_name_set(target, value, _old, _init):
    target.name_bidx = generate_blind_index(value)

@event.listens_for(User.email, "set")
def on_user_email_set(target, value, _old, _init):
    target.email_bidx = generate_blind_index(value)
