import pytest
import sys
import importlib
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.exceptions import ValdrixException

@pytest.fixture
def mock_settings():
    with patch("app.shared.db.session.get_settings") as mock:
        yield mock

class TestSessionExhaustive:
    """Exhaustive tests for session.py to reach 100% coverage."""

    def test_startup_missing_db_url(self):
        """Test sys.exit when DATABASE_URL is missing (lines 20-23)."""
        with patch("app.shared.db.session.get_settings") as mock_settings_fn, \
             patch("sys.exit") as mock_exit:
            
            mock_settings_fn.return_value.DATABASE_URL = None
            # Force reload to trigger top-level checks
            import app.shared.db.session
            importlib.reload(app.shared.db.session)
            
            mock_exit.assert_called_with(1)

    @pytest.mark.parametrize("ssl_mode", ["disable", "require", "verify-ca", "verify-full"])
    def test_engine_creation_ssl_modes(self, ssl_mode):
        """Test engine creation with different SSL modes (lines 35-77)."""
        with patch("app.shared.db.session.get_settings") as mock_settings_fn, \
             patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine:
            
            mock_settings_fn.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings_fn.return_value.DB_SSL_MODE = ssl_mode
            mock_settings_fn.return_value.DB_SSL_CA_CERT_PATH = "/tmp/ca.crt"
            mock_settings_fn.return_value.TESTING = False
            mock_settings_fn.return_value.is_production = False
            
            with patch("ssl.create_default_context") as mock_ssl_ctx:
                import app.shared.db.session
                importlib.reload(app.shared.db.session)
                
                assert mock_create_engine.called

    def test_invalid_ssl_mode(self):
        """Test ValueError for invalid SSL mode (line 77)."""
        with patch("app.shared.db.session.get_settings") as mock_settings_fn:
            mock_settings_fn.return_value.DATABASE_URL = "postgresql://host"
            mock_settings_fn.return_value.DB_SSL_MODE = "invalid"
            
            import app.shared.db.session
            with pytest.raises(ValueError, match="Invalid DB_SSL_MODE"):
                importlib.reload(app.shared.db.session)

    @pytest.mark.asyncio
    async def test_get_db_rls_failure_handling(self):
        """Test exception handling during RLS set in get_db (line 158)."""
        from app.shared.db.session import get_db
        
        mock_request = MagicMock()
        mock_request.state.tenant_id = uuid4()
        
        with patch("app.shared.db.session.async_session_maker") as mock_maker:
            mock_session = AsyncMock(spec=AsyncSession)
            # Simulate Postgres but fail execute
            mock_session.bind.url = "postgresql://host"
            mock_session.execute.side_effect = Exception("RLS Fail")
            mock_maker.return_value = mock_session
            mock_session.__aenter__.return_value = mock_session
            
            # Should catch and log, not raise
            async for _ in get_db(mock_request):
                break

    @pytest.mark.asyncio
    async def test_set_session_tenant_id_exception(self):
        """Test exception handling in set_session_tenant_id (line 197)."""
        from app.shared.db.session import set_session_tenant_id
        
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind.url = "postgresql://host"
        mock_session.execute.side_effect = Exception("Set Context Fail")
        
        # Should not raise
        await set_session_tenant_id(mock_session, uuid4())

    def test_check_rls_policy_enforcement_fail(self):
        """Test RLS enforcement when context is missing and TESTING=False (line 243)."""
        from app.shared.db.session import check_rls_policy
        
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            
            with pytest.raises(ValdrixException, match="RLS context missing"):
                check_rls_policy(mock_conn, None, "SELECT * FROM users", None, None, False)

    def test_check_rls_policy_exempt_tables(self):
        """Test RLS bypass for exempt tables (line 218)."""
        from app.shared.db.session import check_rls_policy
        
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            
            # Should not raise for migration/system tables
            check_rls_policy(mock_conn, None, "SELECT * FROM alembic_version", None, None, False)
            check_rls_policy(mock_conn, None, "SELECT 1", None, None, False)
