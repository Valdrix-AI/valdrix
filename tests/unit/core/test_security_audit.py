import pytest
import os
import base64
from unittest.mock import patch
from cryptography.fernet import Fernet, MultiFernet
from app.shared.core.security import (
    EncryptionKeyManager, encrypt_string, decrypt_string, 
    generate_blind_index, generate_new_key
)

@pytest.fixture
def mock_settings():
    with patch("app.shared.core.security.get_settings") as mock:
        mock.return_value.ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock.return_value.API_KEY_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock.return_value.PII_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock.return_value.LEGACY_ENCRYPTION_KEYS = []
        mock.return_value.BLIND_INDEX_KEY = "blind-index-secret"
        yield mock.return_value

@pytest.fixture(autouse=True)
def set_env():
    with patch.dict(os.environ, {"KDF_SALT": base64.b64encode(os.urandom(32)).decode(), "ENVIRONMENT": "development"}):
        yield

class TestEncryptionKeyManager:
    def test_generate_salt(self):
        salt = EncryptionKeyManager.generate_salt()
        assert len(base64.b64decode(salt)) == 32

    def test_get_or_create_salt_env(self):
        with patch.dict(os.environ, {"KDF_SALT": "configured-salt"}):
            assert EncryptionKeyManager.get_or_create_salt() == "configured-salt"

    def test_get_or_create_salt_dev_fallback(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            if "KDF_SALT" in os.environ:
                del os.environ["KDF_SALT"]
            salt = EncryptionKeyManager.get_or_create_salt()
            assert salt is not None

    def test_get_or_create_salt_prod_fail(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            if "KDF_SALT" in os.environ:
                del os.environ["KDF_SALT"]
            with pytest.raises(ValueError, match="CRITICAL: KDF_SALT environment variable not set"):
                EncryptionKeyManager.get_or_create_salt()

    def test_derive_key(self):
        master = Fernet.generate_key().decode()
        salt = EncryptionKeyManager.generate_salt()
        key1 = EncryptionKeyManager.derive_key(master, salt, key_version=1)
        key2 = EncryptionKeyManager.derive_key(master, salt, key_version=1)
        key3 = EncryptionKeyManager.derive_key(master, salt, key_version=2)
        
        assert key1 == key2
        assert key1 != key3
        # Should be base64 urlsafe
        base64.urlsafe_b64decode(key1)

    def test_create_fernet_for_key(self):
        master = Fernet.generate_key().decode()
        salt = EncryptionKeyManager.generate_salt()
        fernet = EncryptionKeyManager.create_fernet_for_key(master, salt)
        assert isinstance(fernet, Fernet)

    def test_create_multi_fernet(self, mock_settings):
        salt = EncryptionKeyManager.generate_salt()
        primary = mock_settings.ENCRYPTION_KEY
        mf = EncryptionKeyManager.create_multi_fernet(primary, salt=salt)
        assert isinstance(mf, MultiFernet)

def test_encrypt_decrypt_roundtrip(mock_settings):
    original = "secret-message-123"
    
    # Generic context
    encrypted = encrypt_string(original, context="generic")
    assert encrypted != original
    decrypted = decrypt_string(encrypted, context="generic")
    assert decrypted == original

def test_context_specific_encryption(mock_settings):
    original = "sensitive"
    
    # Different keys for different contexts should produce different ciphertexts (even if primary keys were same, KDF uses versioning/context if we added it, but here it uses different setting keys)
    enc_api = encrypt_string(original, context="api_key")
    enc_pii = encrypt_string(original, context="pii")
    
    assert enc_api != enc_pii
    
    # Cross-decryption should fail (different keys)
    assert decrypt_string(enc_api, context="pii") is None
    assert decrypt_string(enc_pii, context="api_key") is None

def test_generate_blind_index(mock_settings):
    val = "  User@Example.com  "
    idx1 = generate_blind_index(val)
    idx2 = generate_blind_index("user@example.com")
    idx3 = generate_blind_index("other@example.com")
    
    assert idx1 == idx2
    assert idx1 != idx3
    assert len(idx1) == 64 # SHA256 hex

def test_generate_new_key():
    key = generate_new_key()
    # Should be valid Fernet key
    Fernet(key.encode())

def test_decrypt_invalid_input():
    assert decrypt_string(None) is None
    assert decrypt_string("") is None
    assert decrypt_string("invalid-base64-or-fernet") is None

def test_legacy_keys_support(mock_settings):
    legacy_key = Fernet.generate_key().decode()
    mock_settings.LEGACY_ENCRYPTION_KEYS = [legacy_key]
    
    original = "legacy-secret"
    # Encrypt with primary
    token = encrypt_string(original)
    
    # Decrypt should work
    assert decrypt_string(token) == original
    
    # Encrypt with legacy (simulating old data)
    fer_legacy = EncryptionKeyManager.create_fernet_for_key(legacy_key, EncryptionKeyManager.get_or_create_salt())
    legacy_token = fer_legacy.encrypt(original.encode()).decode()
    
    # Decrypt with MultiFernet (which has legacy key) should work
    assert decrypt_string(legacy_token) == original

def test_internal_fernet_helpers(mock_settings):
    from app.shared.core.security import _get_api_key_fernet, _get_pii_fernet, _get_multi_fernet
    
    assert isinstance(_get_api_key_fernet(), MultiFernet)
    assert isinstance(_get_pii_fernet(), MultiFernet)
    assert isinstance(_get_multi_fernet(None), MultiFernet)

def test_blind_index_edge_cases(mock_settings):
    assert generate_blind_index("") is None
    
    mock_settings.BLIND_INDEX_KEY = None
    mock_settings.ENCRYPTION_KEY = None
    assert generate_blind_index("val") is None

def test_kdf_invalid_salt():
    with pytest.raises(ValueError, match="Invalid KDF salt format"):
        EncryptionKeyManager.derive_key("master", "not-base64-!!!")

def test_create_multi_fernet_invalid_key():
    # If a key is invalid, it should be skipped but not crash the whole thing
    mf = EncryptionKeyManager.create_multi_fernet("invalid-key", legacy_keys=("valid-but-not-really",))
    assert isinstance(mf, MultiFernet)
