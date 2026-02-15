import hashlib
import hmac
import base64
import binascii
import os
import secrets
import structlog
from functools import lru_cache
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.shared.core.config import get_settings

logger = structlog.get_logger()

# ============================================================================
# Encryption Key Manager (Production Hardening)
# ============================================================================


class EncryptionKeyManager:
    """
    PRODUCTION: Manages encryption keys with versioning and rotation.

    Features:
    - Random salt per environment (not hardcoded)
    - Key versioning for rotation
    - Decryption support with fallback keys during rotation
    - Secure KDF with PBKDF2-SHA256
    """

    # KDF Constants
    KDF_ITERATIONS = 100000  # NIST recommends 100,000+
    KDF_SALT_LENGTH = 32  # 256 bits

    @staticmethod
    def generate_salt() -> str:
        """Generate a cryptographically secure random salt."""
        random_bytes = secrets.token_bytes(EncryptionKeyManager.KDF_SALT_LENGTH)
        return base64.b64encode(random_bytes).decode("utf-8")

    @staticmethod
    def get_or_create_salt() -> str:
        """Get KDF salt from environment variable."""
        settings = get_settings()
        salt = os.environ.get("KDF_SALT") or getattr(settings, "KDF_SALT", None)
        if salt:
            return str(salt)

        # Production-grade: never generate salts at runtime, even in development.
        raise ValueError(
            "KDF_SALT is required for encryption stability and must be set in the environment "
            "(base64-encoded random 32 bytes)."
        )

    @staticmethod
    @lru_cache(maxsize=32)
    def derive_key(
        master_key: str,
        salt: str,
        key_version: int = 1,
        iterations: int = KDF_ITERATIONS,
    ) -> bytes:
        """Derive an encryption key from master key using PBKDF2."""
        try:
            salt_bytes = base64.b64decode(salt, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"Invalid KDF salt format: {str(e)}") from e

        if len(salt_bytes) != EncryptionKeyManager.KDF_SALT_LENGTH:
            raise ValueError(
                f"Invalid KDF salt length: expected {EncryptionKeyManager.KDF_SALT_LENGTH} bytes, got {len(salt_bytes)}"
            )

        kdf_input = f"{master_key}:v{key_version}".encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=iterations,
        )

        derived_key = kdf.derive(kdf_input)
        return base64.urlsafe_b64encode(derived_key)

    @staticmethod
    @lru_cache(maxsize=32)
    def create_fernet_for_key(master_key: str, salt: str) -> Fernet:
        derived_key = EncryptionKeyManager.derive_key(master_key, salt)
        return Fernet(derived_key)

    @staticmethod
    @lru_cache(maxsize=16)
    def create_multi_fernet(
        primary_key: str,
        fallback_keys: tuple[str, ...] | None = None,
        salt: str | None = None,
    ) -> MultiFernet:
        """Create MultiFernet for key rotation support."""
        if salt is None:
            salt = EncryptionKeyManager.get_or_create_salt()

        all_keys = [primary_key]
        if fallback_keys:
            all_keys.extend(fallback_keys)

        fernet_instances: list[Fernet] = []

        for idx, key in enumerate(all_keys):
            try:
                fernet = EncryptionKeyManager.create_fernet_for_key(key, salt)
                fernet_instances.append(fernet)
            except ValueError as e:
                logger.error(
                    "fernet_creation_failed",
                    key_index=idx,
                    is_primary=(idx == 0),
                    error=str(e),
                )
                # Primary key must always work; fallback keys are best-effort.
                if idx == 0:
                    raise

        if not fernet_instances:
            raise ValueError("No valid encryption keys could be derived")

        return MultiFernet(fernet_instances)


# ============================================================================
# Encryption Functions
# ============================================================================


def _get_api_key_fernet() -> MultiFernet:
    settings = get_settings()
    fallback_keys = (
        tuple(settings.ENCRYPTION_FALLBACK_KEYS)
        if settings.ENCRYPTION_FALLBACK_KEYS
        else None
    )

    return _get_multi_fernet(
        settings.API_KEY_ENCRYPTION_KEY or settings.ENCRYPTION_KEY, fallback_keys
    )


def _get_pii_fernet() -> MultiFernet:
    settings = get_settings()
    fallback_keys = (
        tuple(settings.ENCRYPTION_FALLBACK_KEYS)
        if settings.ENCRYPTION_FALLBACK_KEYS
        else None
    )
    return _get_multi_fernet(
        settings.PII_ENCRYPTION_KEY or settings.ENCRYPTION_KEY, fallback_keys
    )


def _get_multi_fernet(
    primary_key: str | None,
    fallback_keys: list[str] | tuple[str, ...] | None = None,
) -> MultiFernet:
    """Returns a MultiFernet instance for secret rotation."""
    if not primary_key:
        raise ValueError("ENCRYPTION_KEY must be set for secure encryption.")

    # Ensure list is converted to tuple for lru_cache hashing
    fallback_tuple: tuple[str, ...] | None = (
        tuple(fallback_keys) if isinstance(fallback_keys, list) else fallback_keys
    )

    return EncryptionKeyManager.create_multi_fernet(
        primary_key=primary_key, fallback_keys=fallback_tuple
    )


def encrypt_string(value: str, context: str = "generic") -> str | None:
    """
    Symmetrically encrypt a string with hardened salt management.
    """
    if not value:
        return None

    settings = get_settings()
    # SEC-06: Choose context-specific key material
    if context == "api_key":
        primary_key = settings.API_KEY_ENCRYPTION_KEY or settings.ENCRYPTION_KEY
    elif context == "pii":
        primary_key = settings.PII_ENCRYPTION_KEY or settings.ENCRYPTION_KEY
    else:
        primary_key = settings.ENCRYPTION_KEY

    fernet = _get_multi_fernet(
        primary_key,
        tuple(settings.ENCRYPTION_FALLBACK_KEYS)
        if settings.ENCRYPTION_FALLBACK_KEYS
        else None,
    )

    return fernet.encrypt(value.encode()).decode()


def decrypt_string(value: str, context: str = "generic") -> str | None:
    """
    Symmetrically decrypt a string with hardened salt management.
    """
    if not value:
        return None

    try:
        settings = get_settings()
        # SEC-06: Choose context-specific key material
        if context == "api_key":
            primary_key = settings.API_KEY_ENCRYPTION_KEY or settings.ENCRYPTION_KEY
        elif context == "pii":
            primary_key = settings.PII_ENCRYPTION_KEY or settings.ENCRYPTION_KEY
        else:
            primary_key = settings.ENCRYPTION_KEY

        fernet = _get_multi_fernet(
            primary_key,
            tuple(settings.ENCRYPTION_FALLBACK_KEYS)
            if settings.ENCRYPTION_FALLBACK_KEYS
            else None,
        )

        return fernet.decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as e:
        logger.error("decryption_failed", context=context, error=str(e), exc_info=True)
        # Fail closed in staging/production to avoid silent data loss
        settings = get_settings()
        environment = getattr(settings, "ENVIRONMENT", "development")
        if getattr(settings, "TESTING", False):
            return None
        if environment in ["production", "staging"]:
            from app.shared.core.exceptions import DecryptionError

            raise DecryptionError(details={"context": context}) from e
        return None


def generate_blind_index(value: str) -> str | None:
    """
    Generates a deterministic hash for searchable encryption.
    """
    if not value or value == "":
        return None

    settings = get_settings()
    key_str = settings.BLIND_INDEX_KEY or settings.ENCRYPTION_KEY
    if not key_str:
        return None

    key = key_str.encode()
    normalized_value = str(value).strip().lower()

    return hmac.new(key, normalized_value.encode(), hashlib.sha256).hexdigest()


def generate_secret_blind_index(value: str) -> str | None:
    """
    Generates a deterministic hash for secrets (tokens/keys) where case must be preserved.

    This is intentionally NOT lowercased to avoid reducing entropy for bearer tokens.
    """
    if not value:
        return None

    settings = get_settings()
    key_str = settings.BLIND_INDEX_KEY or settings.ENCRYPTION_KEY
    if not key_str:
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None

    key = key_str.encode()
    return hmac.new(key, normalized_value.encode(), hashlib.sha256).hexdigest()


def generate_new_key() -> str:
    """Generate a new Fernet key."""
    return Fernet.generate_key().decode()
