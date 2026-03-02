"""
Tests for Auth Blocking of Soft-Deleted Tenants

Covers:
- SEC-HAR-13: get_current_user raises 403 if tenant is soft-deleted (Finding #H18)
- Validates both optional and non-optional column paths
"""

import os
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-testing-at-least-32-bytes")
os.environ.setdefault("ENCRYPTION_KEY", "32-byte-long-test-encryption-key")
os.environ.setdefault("CSRF_SECRET_KEY", "test-csrf-secret-key-at-least-32-bytes")
os.environ.setdefault("KDF_SALT", "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=")
os.environ.setdefault("DB_SSL_MODE", "disable")
os.environ.setdefault("is_production", "false")

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.models.tenant import UserRole


class TestAuthBlockingSoftDeletedTenants:
    """Tests for SEC-HAR-13: Auth must fail-fast on soft-deleted tenants."""

    @pytest.mark.asyncio
    async def test_soft_deleted_tenant_raises_403(self):
        """get_current_user must raise HTTP 403 when tenant is_deleted is True."""

        user_id = uuid4()
        tenant_id = uuid4()

        # Mock DB session that returns a row with is_deleted=True
        mock_db = AsyncMock()

        # Row: (id, tenant_id, role, persona, is_active, plan, is_deleted)
        mock_row = (user_id, tenant_id, UserRole.ADMIN.value, "engineering", True, "pro", True)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        # begin_nested context manager
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock()
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested = MagicMock(return_value=mock_ctx)

        # Mock request and credentials
        mock_request = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = "fake.jwt.token"

        with patch("app.shared.core.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "email": "victim@valdrics.io",
            }

            from app.shared.core.auth import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request,
                    credentials=mock_credentials,
                    db=mock_db,
                )

            assert exc_info.value.status_code == 403
            assert "deactivated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_active_tenant_passes_auth(self):
        """get_current_user must succeed when tenant is_deleted is False."""

        user_id = uuid4()
        tenant_id = uuid4()

        mock_db = AsyncMock()

        # is_deleted = False
        mock_row = (user_id, tenant_id, UserRole.ADMIN.value, "engineering", True, "pro", False)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock()
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested = MagicMock(return_value=mock_ctx)

        mock_request = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = "fake.jwt.token"

        with patch("app.shared.core.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "sub": str(user_id),
                "email": "user@valdrics.io",
            }

            from app.shared.core.auth import get_current_user

            user = await get_current_user(
                request=mock_request,
                credentials=mock_credentials,
                db=mock_db,
            )

            assert user.id == user_id
            assert user.tenant_id == tenant_id
