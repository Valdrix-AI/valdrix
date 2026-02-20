"""
Tests for Tenant Soft-Delete and Blind Index Listener Behavior

Covers:
- SEC-HAR-12: Soft-delete fields (deleted_at, is_deleted) on Tenant model
- SEC-HAR-11: SQLAlchemy event listeners for salted blind indexes
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
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.models.tenant import Tenant, User


@pytest_asyncio.fixture
async def db_session():
    """Self-contained async SQLite session for tenant tests."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.shared.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    await engine.dispose()


class TestTenantSoftDelete:
    """Tests for SEC-HAR-12: Tenant Soft-Delete (Finding #H18)."""

    @pytest.mark.asyncio
    async def test_tenant_defaults_to_not_deleted(self, db_session):
        """New tenant is_deleted should default to False."""
        tenant = Tenant(id=uuid4(), name="Active Corp", plan="pro")
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.is_deleted is False
        assert tenant.deleted_at is None

    @pytest.mark.asyncio
    async def test_soft_delete_sets_fields(self, db_session):
        """Marking a tenant as soft-deleted sets both fields."""
        tenant = Tenant(id=uuid4(), name="Deletable Corp", plan="free")
        db_session.add(tenant)
        await db_session.commit()

        # Soft delete
        tenant.is_deleted = True
        tenant.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.is_deleted is True
        assert tenant.deleted_at is not None
        assert isinstance(tenant.deleted_at, datetime)

    @pytest.mark.asyncio
    async def test_soft_delete_preserves_data(self, db_session):
        """Soft-deleted tenant data is still queryable (not physically removed)."""
        tenant_id = uuid4()
        tenant = Tenant(id=tenant_id, name="Preserved Corp", plan="growth")
        db_session.add(tenant)
        await db_session.commit()

        # Soft delete
        tenant.is_deleted = True
        tenant.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        # Re-query to verify data is preserved
        from sqlalchemy import select

        result = await db_session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.name == "Preserved Corp"
        assert found.is_deleted is True


class TestBlindIndexListeners:
    """Tests for SQLAlchemy event listeners generating salted blind indexes.

    The listeners on Tenant.name and User.email should pass
    the tenant_id as a salt to generate_blind_index for cross-tenant isolation.
    """

    @patch("app.models.tenant.generate_blind_index")
    def test_tenant_name_listener_passes_tenant_id(self, mock_bidx):
        """on_tenant_name_set should call generate_blind_index with tenant_id."""
        mock_bidx.return_value = "hashed_name"

        tenant = MagicMock(spec=Tenant)
        tenant.id = uuid4()

        # Simulate the event
        from app.models.tenant import on_tenant_name_set

        on_tenant_name_set(tenant, "New Name", "Old Name", False)

        mock_bidx.assert_called_once_with("New Name", tenant_id=tenant.id)
        assert tenant.name_bidx == "hashed_name"

    @patch("app.models.tenant.generate_blind_index")
    def test_user_email_listener_passes_tenant_id(self, mock_bidx):
        """on_user_email_set should call generate_blind_index with user's tenant_id."""
        mock_bidx.return_value = "hashed_email"

        user = MagicMock(spec=User)
        user.tenant_id = uuid4()

        from app.models.tenant import on_user_email_set

        on_user_email_set(user, "new@example.com", "old@example.com", False)

        mock_bidx.assert_called_once_with("new@example.com", tenant_id=user.tenant_id)
        assert user.email_bidx == "hashed_email"

    @patch("app.models.tenant.generate_blind_index")
    def test_tenant_name_listener_skips_same_value(self, mock_bidx):
        """Listener should not regenerate hash if value hasn't changed."""
        tenant = MagicMock(spec=Tenant)
        tenant.id = uuid4()

        from app.models.tenant import on_tenant_name_set

        on_tenant_name_set(tenant, "Same Name", "Same Name", False)

        mock_bidx.assert_not_called()
