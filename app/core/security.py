import sys
from cryptography.fernet import Fernet
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

_fallback_key = Fernet.generate_key()


def get_fernet() -> Fernet:
    """Initialize Fernet with the encryption key."""
    key = settings.ENCRYPTION_KEY
    if not key:
        if not settings.DEBUG:
            # CRITICAL: Missing encryption key in production is a fatal error.
            # We must fail fast to prevent data loss (encrypting with temp key).
            logger.critical("PRODUCTION_ENCRYPTION_KEY_MISSING",
                            message="ENCRYPTION_KEY must be set in production environment!")
            sys.exit(1)

        # Fallback for development IF debug mode is on
        logger.warning("security_no_encryption_key_found", fallback="using_temporary_key")
        return Fernet(_fallback_key)

    return Fernet(key.encode())

def encrypt_string(plain_text: str) -> str:
    """Encrypt a string using Fernet symmetric encryption."""
    if not plain_text:
        return ""

    f = get_fernet()
    return f.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text: str) -> str:
    """Decrypt a string using Fernet symmetric encryption."""
    if not encrypted_text:
        return ""

    try:
        f = get_fernet()
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception as e:
        logger.error("security_decryption_failed", error=str(e))
        # Return empty or original if decryption fails (safeguard)
        return ""

def generate_new_key() -> str:
    """Utility to generate a new key for .env."""
    return Fernet.generate_key().decode()
