import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, index=True)
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

class User(Base):
    __tablename__ = "users"

    # We use the Supabase User ID (which is a UUID) as our PK
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    role: Mapped[str] = mapped_column(String, default="member") # owner, admin, member

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
