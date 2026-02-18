from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, Boolean, DateTime, Text, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.shared.db.base import Base
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
from app.models._encryption import get_encryption_key

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

    id: Mapped[UUID] = mapped_column(PG_UUID(), primary_key=True, default=uuid4)
    kid: Mapped[str] = mapped_column(String, unique=True, index=True)

    # Store keys in PEM format (encrypted in production, but here we prioritize persistence)
    private_key_pem: Mapped[str] = mapped_column(
        StringEncryptedType(Text, get_encryption_key, AesEngine, "pkcs5"), nullable=False
    )
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # BE-CONN-2: Key rotation tracking
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=KEY_ROTATION_DAYS),
        nullable=True,
    )
    # BE-CONN-3: Dual-key support - track when this key was replaced
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
