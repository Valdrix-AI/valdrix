import pytest
from unittest.mock import patch

from app.shared.core.security import _get_multi_fernet


def _mock_settings(**overrides):
    class DummySettings:
        TESTING = False
        ENVIRONMENT = "production"
        ENCRYPTION_KEY = None
        ENCRYPTION_FALLBACK_KEYS = []

    for k, v in overrides.items():
        setattr(DummySettings, k, v)
    return DummySettings()


def test_get_multi_fernet_requires_key_in_production():
    mock_settings = _mock_settings(ENVIRONMENT="production", TESTING=False, ENCRYPTION_KEY=None)

    with patch("app.shared.core.security.get_settings", return_value=mock_settings):
        with pytest.raises(ValueError, match="ENCRYPTION_KEY must be set"):
            _get_multi_fernet(None)


def test_get_multi_fernet_allows_dev_fallback():
    mock_settings = _mock_settings(ENVIRONMENT="development", TESTING=False, ENCRYPTION_KEY=None)

    with patch("app.shared.core.security.get_settings", return_value=mock_settings):
        fernet = _get_multi_fernet(None)
        assert fernet is not None
