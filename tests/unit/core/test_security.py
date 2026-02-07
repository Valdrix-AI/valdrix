import pytest
import os
import base64
from unittest.mock import patch
from app.shared.core.security import (
    EncryptionKeyManager, 
    encrypt_string, 
    decrypt_string, 
    generate_blind_index
)

@pytest.fixture
def mock_settings():
    with patch("app.shared.core.security.get_settings") as mock:
        mock.return_value.ENCRYPTION_KEY = "32-byte-long-test-encryption-key"
        mock.return_value.API_KEY_ENCRYPTION_KEY = None
        mock.return_value.PII_ENCRYPTION_KEY = None
        mock.return_value.BLIND_INDEX_KEY = "blind-index-key-for-testing"
        mock.return_value.LEGACY_ENCRYPTION_KEYS = []
        yield mock

@pytest.fixture
def mock_env_salt():
    with patch.dict(os.environ, {"KDF_SALT": "dGVzdC1zYWx0LWZvci10ZXN0aW5nLTMyLWJ5dGVz"}):
        yield

def test_encryption_decryption_cycle(mock_settings, mock_env_salt):
    """Test full encryption/decryption round trip."""
    original = "secret_message"
    encrypted = encrypt_string(original)
    decrypted = decrypt_string(encrypted)
    
    assert original == decrypted
    assert original != encrypted

def test_context_encryption(mock_settings, mock_env_salt):
    """Test context-specific key usage."""
    # Setup specific keys for contexts
    mock_settings.return_value.API_KEY_ENCRYPTION_KEY = "api-key-specific-encryption-key-32"
    mock_settings.return_value.PII_ENCRYPTION_KEY = "pii-data-specific-encryption-key-32"
    
    # Encrypt with different contexts
    enc_generic = encrypt_string("data", context="generic")
    enc_api = encrypt_string("data", context="api_key")
    enc_pii = encrypt_string("data", context="pii")
    
    # They should produce different ciphertexts (even if randomness makes them different anyway, 
    # decrypting with wrong context should fail)
    
    # Decrypt generic with correct context
    assert decrypt_string(enc_generic, context="generic") == "data"
    
    # Decrypt API with correct context
    assert decrypt_string(enc_api, context="api_key") == "data"
    
    # Decrypt PII with correct context
    assert decrypt_string(enc_pii, context="pii") == "data"

def test_kdf_salt_generation():
    """Test salt generation and retrieval."""
    salt = EncryptionKeyManager.generate_salt()
    assert len(base64.b64decode(salt)) == 32
    
    with patch.dict(os.environ, {}, clear=True):
        # Without salt env var, should raise error in prod or warn in dev
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(ValueError, match="KDF_SALT environment variable not set"):
                EncryptionKeyManager.get_or_create_salt()

def test_blind_index_deterministic(mock_settings):
    """Test blind index generation is deterministic."""
    val1 = generate_blind_index("user@example.com")
    val2 = generate_blind_index("user@example.com")
    val3 = generate_blind_index("other@example.com")
    
    assert val1 == val2
    assert val1 != val3

def test_blind_index_normalization(mock_settings):
    """Test blind index normalizes case and whitespace."""
    val1 = generate_blind_index(" user@Example.com ")
    val2 = generate_blind_index("user@example.com")
    
    assert val1 == val2
