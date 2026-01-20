import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

# BE-CONN-2: Default key rotation period
KEY_ROTATION_DAYS = 30


class OIDCKey(Base):
    """
    Persistent OIDC Keys for Workload Identity Federation.
    Ensures that our RSA Key Pair remains consistent across restarts,
    preventing trust breakages with Cloud Providers.
    
    BE-CONN-2/3: Supports key rotation with expires_at and dual-key semantics.
    """
    __tablename__ = "oidc_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kid: Mapped[str] = mapped_column(String, unique=True, index=True)
    
    # Store keys in PEM format (encrypted in production, but here we prioritize persistence)
    private_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # BE-CONN-2: Key rotation tracking
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc) + timedelta(days=KEY_ROTATION_DAYS),
        nullable=True
    )
    # BE-CONN-3: Dual-key support - track when this key was replaced
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
