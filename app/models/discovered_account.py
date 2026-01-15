import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.db.base import Base

class DiscoveredAccount(Base):
    """
    Represents an AWS account discovered via AWS Organizations.
    Helps Management Accounts bulk-onboard their child accounts.
    """
    __tablename__ = "discovered_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # The management connection that discovered this account
    management_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aws_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # status: "discovered", "linked", "ignored"
    status: Mapped[str] = mapped_column(String(20), default="discovered", server_default="discovered")
    
    last_discovered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to the management connection
    management_connection = relationship("AWSConnection", foreign_keys=[management_connection_id])

    def __repr__(self):
        return f"<DiscoveredAccount {self.account_id} ({self.status})>"
