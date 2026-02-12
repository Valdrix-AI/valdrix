import pytest
from app.shared.core.config import Settings

def test_csrf_hardening_production():
    """Verify that default CSRF key is rejected in production."""
    with pytest.raises(ValueError, match="SECURITY ERROR: CSRF_SECRET_KEY must be set"):
        Settings(
            DEBUG=False,
            TESTING=False,
            ENVIRONMENT="production",
            CSRF_SECRET_KEY="dev_secret_key_change_me_in_prod",
            SUPABASE_JWT_SECRET="test_jwt_secret_must_be_long_long_long"
        )

def test_encryption_key_production_validation():
    """Verify encryption key length in production."""
    with pytest.raises(ValueError, match="ENCRYPTION_KEY must be at least 32 characters"):
        Settings(
            DEBUG=False,
            TESTING=False,
            ENVIRONMENT="production",
            ENCRYPTION_KEY="too-short",
            SUPABASE_JWT_SECRET="test_jwt_secret_must_be_long_long_long"
        )
