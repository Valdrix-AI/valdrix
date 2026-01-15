import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
from app.core.config import get_settings

settings = get_settings()

def _get_fernet() -> Fernet:
    """Helper to initialize Fernet with the app's encryption key."""
    settings = get_settings()
    # Fernet requires a 32-byte base64 encoded key.
    # We derive this from the ENCRYPTION_KEY string.
    key = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_string(value: str) -> str:
    """Symmetrically encrypt a string (for API keys, etc)."""
    if not value or value == "":
        return None
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()

def decrypt_string(value: str) -> str:
    """Symmetrically decrypt a string."""
    if not value or value == "":
        return None
    f = _get_fernet()
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        # If decryption fails (e.g., bad key), return None instead of crashing
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
    key = settings.ENCRYPTION_KEY.encode()
    
    # Normalize (lowercase) for consistent indexing of emails/names
    normalized_value = str(value).strip().lower()
    
    return hmac.new(key, normalized_value.encode(), hashlib.sha256).hexdigest()
