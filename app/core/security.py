import hashlib
import hmac
import base64
from cryptography.fernet import Fernet, MultiFernet
from typing import Optional, List

from app.core.config import get_settings
# PRODUCTION FIX #6: Import from new security_production module
from app.core.security_production import (
    encrypt_string as prod_encrypt,
    decrypt_string as prod_decrypt,
    EncryptionKeyManager,
)

settings = get_settings()

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def _get_multi_fernet(primary_key: Optional[str], legacy_keys: Optional[List[str]] = None) -> MultiFernet:
    """
    Returns a MultiFernet instance for secret rotation.
    Delegates to EncryptionKeyManager for production-grade KDF and salt management.
    """
    # Use EncryptionKeyManager to handle all KDF logic (PBKDF2 SHA256)
    # This automatically includes salt management and versioning
    if not primary_key:
        # Fallback for dev - though EncryptionKeyManager handles this too via env var checks
        settings = get_settings()
        primary_key = settings.ENCRYPTION_KEY or "dev_fallback_key_do_not_use_in_prod"

    return EncryptionKeyManager.create_multi_fernet(
        primary_key=primary_key,
        legacy_keys=legacy_keys
    )

def _get_api_key_fernet() -> MultiFernet:
    settings = get_settings()
    return _get_multi_fernet(
        settings.API_KEY_ENCRYPTION_KEY or settings.ENCRYPTION_KEY,
        settings.LEGACY_ENCRYPTION_KEYS
    )

def _get_pii_fernet() -> MultiFernet:
    settings = get_settings()
    return _get_multi_fernet(
        settings.PII_ENCRYPTION_KEY or settings.ENCRYPTION_KEY,
        settings.LEGACY_ENCRYPTION_KEYS
    )

def encrypt_string(value: str, context: str = "generic") -> str:
    """
    PRODUCTION: Symmetrically encrypt a string with hardened salt management.
    Delegates to security_production for key derivation and encryption.
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
        
    fernet = EncryptionKeyManager.create_multi_fernet(
        primary_key=primary_key,
        legacy_keys=settings.LEGACY_ENCRYPTION_KEYS
    )
    
    return fernet.encrypt(value.encode()).decode()

def decrypt_string(value: str, context: str = "generic") -> str:
    """
    PRODUCTION: Symmetrically decrypt a string with hardened salt management.
    Delegates to security_production for key derivation and decryption.
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
            
        fernet = EncryptionKeyManager.create_multi_fernet(
            primary_key=primary_key,
            legacy_keys=settings.LEGACY_ENCRYPTION_KEYS
        )
            
        return fernet.decrypt(value.encode()).decode()
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("decryption_failed", context=context, error=str(e))
        return None


def generate_blind_index(value: str) -> str:
    """
    Generates a deterministic hash for searchable encryption.
    Uses HMAC-SHA256 with the application's ENCRYPTION_KEY.
    
    This allows us to perform exact-match lookups on encrypted data
    without being able to decrypt the hash back to the original value.
    """
    if not value or value == "":
        return None
    
    settings = get_settings()
    # SEC-06: Use separate key for blind indexing if available
    key_str = settings.BLIND_INDEX_KEY or settings.ENCRYPTION_KEY
    if not key_str:
        return None
        
    key = key_str.encode()
    
    # Normalize (lowercase) for consistent indexing of emails/names
    normalized_value = str(value).strip().lower()
    
    return hmac.new(key, normalized_value.encode(), hashlib.sha256).hexdigest()

def generate_new_key() -> str:
    """Generate a new Fernet key."""
    return Fernet.generate_key().decode()
