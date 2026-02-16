import pytest
import os
import base64
from typing import Any
from unittest.mock import patch
from cryptography.fernet import Fernet, MultiFernet
from app.shared.core.security import (
    EncryptionKeyManager,
    encrypt_string,
    decrypt_string,
    generate_blind_index,
    generate_new_key,
)


@pytest.fixture
def mock_settings() -> Any:
    with patch("app.shared.core.security.get_settings") as mock:
        mock.return_value.ENCRYPTION_KEY = "valid_key_32_bytes_long_exact_len="
        mock.return_value.API_KEY_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock.return_value.PII_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock.return_value.ENCRYPTION_FALLBACK_KEYS = []
        mock.return_value.BLIND_INDEX_KEY = "blind-index-secret"
        mock.return_value.KDF_SALT = "valid_salt"
        mock.return_value.ENVIRONMENT = "production"
        yield mock


@pytest.fixture(autouse=True)
def set_env() -> Any:
    with patch.dict(
        os.environ,
        {
            "KDF_SALT": base64.b64encode(os.urandom(32)).decode(),
            "ENVIRONMENT": "development",
        },
    ):
        yield


class TestEncryptionKeyManager:
    def test_generate_salt(self) -> None:
        salt = EncryptionKeyManager.generate_salt()
        assert len(base64.b64decode(salt)) == 32

    def test_get_or_create_salt_existing(self, mock_settings: Any) -> None:
        mock_settings.return_value.KDF_SALT = "existing_salt"
        salt = EncryptionKeyManager.get_or_create_salt()
        assert salt == "existing_salt"

    def test_get_or_create_salt_env(self) -> None:
        with patch.dict(os.environ, {"KDF_SALT": "configured-salt"}):
            assert EncryptionKeyManager.get_or_create_salt() == "configured-salt"

    def test_get_or_create_salt_dev_fallback(self) -> None:
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            if "KDF_SALT" in os.environ:
                del os.environ["KDF_SALT"]
                
            with patch("app.shared.core.security.get_settings") as mock_settings:
                mock_settings.return_value.KDF_SALT = None
                # Production-grade hardening requires salt even in dev
                with pytest.raises(ValueError, match="KDF_SALT is required"):
                    EncryptionKeyManager.get_or_create_salt()

    def test_get_or_create_salt_prod_fail(self) -> None:
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            if "KDF_SALT" in os.environ:
                del os.environ["KDF_SALT"]
            with pytest.raises(
                ValueError, match="CRITICAL: KDF_SALT environment variable not set"
            ):
                EncryptionKeyManager.get_or_create_salt()

    def test_derive_key(self) -> None:
        master = Fernet.generate_key().decode()
        salt = EncryptionKeyManager.generate_salt()
        key1 = EncryptionKeyManager.derive_key(master, salt, key_version=1)
        key2 = EncryptionKeyManager.derive_key(master, salt, key_version=1)
        key3 = EncryptionKeyManager.derive_key(master, salt, key_version=2)

        assert key1 == key2
        assert key1 != key3
        # Should be base64 urlsafe
        base64.urlsafe_b64decode(key1)

    def test_create_fernet_for_key(self) -> None:
        master = Fernet.generate_key().decode()
        salt = EncryptionKeyManager.generate_salt()
        fernet = EncryptionKeyManager.create_fernet_for_key(master, salt)
        assert isinstance(fernet, Fernet)

    def test_create_multi_fernet(self, mock_settings: Any) -> None:
        salt = EncryptionKeyManager.generate_salt()
        primary = mock_settings.ENCRYPTION_KEY
        mf = EncryptionKeyManager.create_multi_fernet(primary, salt=salt)
        assert isinstance(mf, MultiFernet)

    def test_encrypt_decrypt_string(self, mock_settings: Any) -> None:
        original = "secret_message"
        encrypted = encrypt_string(original)
        assert encrypted != original
        assert encrypted is not None
        decrypted = decrypt_string(encrypted)
        assert decrypted == original

    def test_encrypt_string_none(self, mock_settings: Any) -> None:
        from typing import cast
        assert encrypt_string(cast(str, None)) is None

    def test_decrypt_string_none(self, mock_settings: Any) -> None:
        from typing import cast
        assert decrypt_string(cast(str, None)) is None

    def test_decrypt_string_invalid(self, mock_settings: Any) -> None:
        assert decrypt_string("invalid") is None

    def test_generate_blind_index(self, mock_settings: Any) -> None:
        value = "searchable_value"
        index = generate_blind_index(value)
        assert isinstance(index, str)
        assert len(index) > 0
        # Deterministic check
        assert generate_blind_index(value) == index

    def test_generate_blind_index_none(self, mock_settings: Any) -> None:
        from typing import cast
        assert generate_blind_index(cast(str, None)) is None

    def test_internal_fernet_helpers(self, mock_settings: Any) -> None:
        from app.shared.core.security import (
            _get_multi_fernet,
            _get_api_key_fernet,
            _get_pii_fernet,
        )
        from cryptography.fernet import MultiFernet

        assert isinstance(_get_api_key_fernet(), MultiFernet)
        assert isinstance(_get_pii_fernet(), MultiFernet)
        with pytest.raises(ValueError, match="ENCRYPTION_KEY must be set"):
            _get_multi_fernet(None)


# -- Standalone Function Tests --

def test_encrypt_decrypt_functions(mock_settings: Any) -> None:
    original = "data"
    enc = encrypt_string(original)
    assert enc is not None
    dec = decrypt_string(enc)
    assert dec == original


def test_encrypt_none(mock_settings: Any) -> None:
    from typing import cast
    assert encrypt_string(cast(str, None)) is None


def test_decrypt_none(mock_settings: Any) -> None:
    from typing import cast
    assert decrypt_string(cast(str, None)) is None


def test_encrypt_decrypt_roundtrip(mock_settings: Any) -> None:
    original = "secret-message-123"

    # Generic context
    encrypted = encrypt_string(original, context="generic")
    assert encrypted != original
    assert encrypted is not None
    decrypted = decrypt_string(encrypted, context="generic")
    assert decrypted == original


def test_context_specific_encryption(mock_settings: Any) -> None:
    original = "sensitive"

    # Different keys for different contexts
    enc_api = encrypt_string(original, context="api_key")
    enc_pii = encrypt_string(original, context="pii")

    assert enc_api is not None
    assert enc_pii is not None
    assert enc_api != enc_pii

    # Cross-decryption should fail (different keys)
    assert decrypt_string(enc_api, context="pii") is None
    assert decrypt_string(enc_pii, context="api_key") is None


def test_generate_blind_index(mock_settings: Any) -> None:
    val = "  User@Example.com  "
    idx1 = generate_blind_index(val)
    idx2 = generate_blind_index("user@example.com")
    idx3 = generate_blind_index("other@example.com")

    assert idx1 == idx2
    assert idx1 != idx3
    assert idx1 is not None
    assert len(idx1) == 64  # SHA256 hex


def test_generate_new_key() -> None:
    key = generate_new_key()
    # Should be valid Fernet key
    Fernet(key.encode())


def test_decrypt_invalid_input() -> None:
    # mypy complains about passing None to a function expecting str, 
    # but we are testing runtime robustness
    from typing import cast
    assert decrypt_string(cast(str, None)) is None
    assert decrypt_string("") is None
    assert decrypt_string("invalid-base64-or-fernet") is None


def test_fallback_keys_support(mock_settings: Any) -> None:
    fallback_key = Fernet.generate_key().decode()
    mock_settings.ENCRYPTION_FALLBACK_KEYS = [fallback_key]

    original = "fallback-secret"
    # Encrypt with primary
    # Encrypt with primary
    token = encrypt_string(original)
    assert token is not None

    # Decrypt should work
    assert decrypt_string(token) == original

    # Encrypt with fallback key (simulating previously encrypted data)
    fer_fallback = EncryptionKeyManager.create_fernet_for_key(
        fallback_key, EncryptionKeyManager.get_or_create_salt()
    )
    fallback_token = fer_fallback.encrypt(original.encode()).decode()

    # Decrypt with MultiFernet (which includes fallback key) should work
    assert decrypt_string(fallback_token) == original


def test_internal_fernet_helpers(mock_settings: Any) -> None:
    from app.shared.core.security import (
        _get_api_key_fernet,
        _get_pii_fernet,
        _get_multi_fernet,
    )
    from cryptography.fernet import MultiFernet

    assert isinstance(_get_api_key_fernet(), MultiFernet)
    assert isinstance(_get_pii_fernet(), MultiFernet)
    with pytest.raises(ValueError, match="ENCRYPTION_KEY must be set"):
        _get_multi_fernet(None)


def test_blind_index_edge_cases(mock_settings: Any) -> None:
    assert generate_blind_index("") is None

    mock_settings.BLIND_INDEX_KEY = None
    mock_settings.ENCRYPTION_KEY = None
    assert generate_blind_index("val") is None


def test_kdf_invalid_salt() -> None:
    with pytest.raises(ValueError, match="Invalid KDF salt format"):
        EncryptionKeyManager.derive_key("master", "not-base64-!!!")


def test_create_multi_fernet_invalid_key() -> None:
    # If a key is invalid, it should be skipped but not crash the whole thing
    mf = EncryptionKeyManager.create_multi_fernet(
        "invalid-key", fallback_keys=("valid-but-not-really",)
    )
    assert isinstance(mf, MultiFernet)
