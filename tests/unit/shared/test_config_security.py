import pytest
from pydantic import ValidationError
from app.shared.core.config import Settings

FAKE_KDF_SALT = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s="


def test_csrf_hardening_production():
    """Verify that default CSRF key is rejected in production."""
    with pytest.raises(
        ValidationError,
        match="SECURITY ERROR: CSRF_SECRET_KEY must be set to a non-default secure value",
    ):
        Settings(
            DEBUG=False,
            TESTING=False,
            ENVIRONMENT="production",
            CSRF_SECRET_KEY="dev_secret_key_change_me_in_prod",
            ENCRYPTION_KEY="k" * 32,
            KDF_SALT=FAKE_KDF_SALT,
            SUPABASE_JWT_SECRET="test_jwt_secret_must_be_long_long_long",
        )


def test_encryption_key_production_validation():
    """Verify encryption key length in production."""
    with pytest.raises(
        ValidationError, match="ENCRYPTION_KEY must be set to a secure value"
    ):
        Settings(
            DEBUG=False,
            TESTING=False,
            ENVIRONMENT="production",
            ENCRYPTION_KEY="too-short",
            CSRF_SECRET_KEY="c" * 32,
            KDF_SALT=FAKE_KDF_SALT,
            SUPABASE_JWT_SECRET="test_jwt_secret_must_be_long_long_long",
        )
