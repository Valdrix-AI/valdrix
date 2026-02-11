import pytest
from unittest.mock import patch

from app.shared.core.security import _get_api_key_fernet, decrypt_string, encrypt_string
from app.shared.core.exceptions import DecryptionError


class DummySettings:
    ENCRYPTION_KEY = None
    API_KEY_ENCRYPTION_KEY = None
    PII_ENCRYPTION_KEY = None
    ENCRYPTION_FALLBACK_KEYS = []
    BLIND_INDEX_KEY = None
    TESTING = True
    ENVIRONMENT = "development"


class DummyProdSettings:
    ENCRYPTION_KEY = "prod-encryption-key-32-bytes-minimum"
    API_KEY_ENCRYPTION_KEY = None
    PII_ENCRYPTION_KEY = None
    ENCRYPTION_FALLBACK_KEYS = []
    BLIND_INDEX_KEY = None
    TESTING = False
    ENVIRONMENT = "production"


def test_get_api_key_fernet_uses_fallback_in_dev():
    with patch("app.shared.core.security.get_settings", return_value=DummySettings()):
        fernet = _get_api_key_fernet()
        assert fernet is not None


def test_encrypt_decrypt_fallback_in_dev():
    with patch("app.shared.core.security.get_settings", return_value=DummySettings()):
        token = encrypt_string("secret")
        assert token is not None
        assert decrypt_string(token) == "secret"


def test_decrypt_raises_in_production_on_invalid_ciphertext():
    with patch("app.shared.core.security.get_settings", return_value=DummyProdSettings()):
        with pytest.raises(DecryptionError):
            decrypt_string("invalid-base64-or-fernet")
