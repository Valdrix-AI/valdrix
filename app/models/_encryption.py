"""
Centralized lazy encryption key resolver for ORM column definitions.

StringEncryptedType accepts a callable for the `key` parameter, which is
evaluated at encrypt/decrypt time rather than at import time. This decouples
model imports from the ENCRYPTION_KEY environment variable, enabling:

- Tests to import models without requiring ENCRYPTION_KEY
- Tooling and scripts to introspect models without full environment setup
- Fail-fast at first actual encryption operation, not at import

Usage in models:
    from app.models._encryption import get_encryption_key
    ...
    name: Mapped[str] = mapped_column(
        StringEncryptedType(String, get_encryption_key, AesEngine, "pkcs5")
    )
"""

from typing import Optional

_cached_key: Optional[str] = None


def get_encryption_key() -> str:
    """
    Lazily resolve the encryption key from settings.

    The result is cached after the first call to avoid repeated config lookups
    on every column access. Raises RuntimeError if ENCRYPTION_KEY is not set.
    """
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    from app.shared.core.config import get_settings

    settings = get_settings()
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY not set. Cannot perform encryption operations. "
            "Set the ENCRYPTION_KEY environment variable before accessing encrypted data."
        )
    _cached_key = key
    return _cached_key


def clear_encryption_key_cache() -> None:
    """
    Clear the cached encryption key.

    Useful for testing or key rotation scenarios.
    """
    global _cached_key
    _cached_key = None
