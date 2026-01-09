import uuid
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, index=True)
    plan: Mapped[str] = mapped_column(String, default="free")  # free, starter, pro
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete")

        # Add this line in the Tenant class
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