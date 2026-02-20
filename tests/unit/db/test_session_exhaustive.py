import pytest
import time
import importlib
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
import app.shared.db.session as session_mod
from app.shared.core.config import get_settings
from app.shared.core.exceptions import ValdrixException


@pytest.fixture
def clean_session_module():
    """Ensure session module is clean before and after tests."""
    # Restore valid state for reload
    with patch.dict(
        "os.environ",
        {"DATABASE_URL": "postgresql+asyncpg://user@host/db", "TESTING": "True"},
    ):
        get_settings.cache_clear()
        yield
        importlib.reload(session_mod)


class TestSessionExhaustive:
    """Exhaustive tests for db/session.py using reload."""

    def test_missing_db_url_fails_on_runtime_init(self, clean_session_module):
        """Test that missing DATABASE_URL fails when DB runtime initializes."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = ""
        mock_settings.DB_SSL_MODE = "disable"
        mock_settings.TESTING = False
        mock_settings.is_production = False
        mock_settings.DEBUG = True

        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            importlib.reload(session_mod)
            with pytest.raises(
                ValueError, match="DATABASE_URL is not set. The application cannot start."
            ):
                session_mod._get_db_runtime()

    def test_ssl_modes_exhaustive(self, clean_session_module):
        """Test all SSL mode branches."""
        # Create dummy cert file to avoid FileNotFoundError
        cert_path = "/tmp/ca.crt"
        with open(cert_path, "w") as f:
            f.write("dummy cert")

        modes = ["disable", "require", "verify-ca", "verify-full"]
        for mode in modes:
            mock_settings = MagicMock()
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user@host/db"
            mock_settings.DB_SSL_MODE = mode
            mock_settings.DB_SSL_CA_CERT_PATH = cert_path if "verify" in mode else ""
            mock_settings.DEBUG = True
            mock_settings.TESTING = False
            mock_settings.DB_POOL_SIZE = 10
            mock_settings.DB_MAX_OVERFLOW = 20
            mock_settings.DB_ECHO = False
            # Ensure is_production doesn't default to True (MagicMock is truthy)
            mock_settings.is_production = False
            # Ensure DEBUG is available for engine creation
            mock_settings.DEBUG = True

            with patch(
                "app.shared.core.config.get_settings", return_value=mock_settings
            ):
                if "verify" in mode:
                    with patch("ssl.create_default_context") as mock_ctx:
                        mock_ctx.return_value = MagicMock()
                        importlib.reload(session_mod)
                else:
                    importlib.reload(session_mod)

    def test_production_ssl_requirement(self, clean_session_module):
        """Test that production mode requires CA cert for SSL."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user@host/db"
        mock_settings.DB_SSL_MODE = "require"
        mock_settings.DB_SSL_CA_CERT_PATH = ""
        mock_settings.is_production = True

        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            importlib.reload(session_mod)
            with pytest.raises(ValueError, match="DB_SSL_CA_CERT_PATH is mandatory"):
                session_mod._get_db_runtime()

    def test_invalid_ssl_mode(self, clean_session_module):
        """Test error on invalid SSL mode."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://h/d"
        mock_settings.DB_SSL_MODE = "invalid"
        mock_settings.is_production = False

        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            importlib.reload(session_mod)
            with pytest.raises(ValueError, match="Invalid DB_SSL_MODE"):
                session_mod._get_db_runtime()

    def test_pool_settings_exhaustive(self, clean_session_module):
        """Test pool class and settings branches."""
        # SQLite pool
        mock_settings_sqlite = MagicMock()
        mock_settings_sqlite.DATABASE_URL = "sqlite+aiosqlite:///tmp/test.db"
        mock_settings_sqlite.TESTING = False
        mock_settings_sqlite.DB_SSL_MODE = "disable"
        mock_settings_sqlite.is_production = False

        with (
            patch(
                "app.shared.core.config.get_settings", return_value=mock_settings_sqlite
            ),
            patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create,
            patch("sqlalchemy.event.listens_for"),
        ):
            importlib.reload(session_mod)
            session_mod._get_db_runtime()
            mock_create.assert_called()
            _, kwargs = mock_create.call_args
            assert kwargs["poolclass"].__name__ == "StaticPool"

        # Testing pool
        mock_settings_testing = MagicMock()
        mock_settings_testing.DATABASE_URL = "postgresql+asyncpg://h/d"
        mock_settings_testing.TESTING = True
        mock_settings_testing.DB_SSL_MODE = "disable"
        mock_settings_testing.is_production = False

        with (
            patch(
                "app.shared.core.config.get_settings",
                return_value=mock_settings_testing,
            ),
            patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create,
            patch("sqlalchemy.event.listens_for"),
        ):
            importlib.reload(session_mod)
            session_mod._get_db_runtime()
            _, kwargs = mock_create.call_args
            # Now correctly expects StaticPool because safety swap defaults to SQLite memory
            assert kwargs["poolclass"].__name__ == "StaticPool"

        # PostgreSQL queue pool by default
        mock_settings_pg = MagicMock()
        mock_settings_pg.DATABASE_URL = "postgresql+asyncpg://h/d"
        mock_settings_pg.TESTING = False
        mock_settings_pg.DB_SSL_MODE = "disable"
        mock_settings_pg.is_production = False
        mock_settings_pg.DB_USE_NULL_POOL = False
        mock_settings_pg.DB_EXTERNAL_POOLER = False
        mock_settings_pg.DB_POOL_SIZE = 11
        mock_settings_pg.DB_MAX_OVERFLOW = 7
        mock_settings_pg.DB_POOL_TIMEOUT = 9
        mock_settings_pg.DB_POOL_RECYCLE = 60
        mock_settings_pg.DB_ECHO = False

        with (
            patch(
                "app.shared.core.config.get_settings",
                return_value=mock_settings_pg,
            ),
            patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create,
            patch("sqlalchemy.event.listens_for"),
        ):
            importlib.reload(session_mod)
            session_mod._get_db_runtime()
            _, kwargs = mock_create.call_args
            assert "poolclass" not in kwargs
            assert kwargs["pool_size"] == 11
            assert kwargs["max_overflow"] == 7
            assert kwargs["pool_timeout"] == 9

    def test_verify_ca_mode_requirements(self, clean_session_module):
        """Test verify-ca requirement for CA cert path."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://h/d"
        mock_settings.DB_SSL_MODE = "verify-ca"
        mock_settings.DB_SSL_CA_CERT_PATH = ""
        mock_settings.is_production = False

        with patch("app.shared.core.config.get_settings", return_value=mock_settings):
            importlib.reload(session_mod)
            with pytest.raises(ValueError, match="DB_SSL_CA_CERT_PATH required"):
                session_mod._get_db_runtime()

    def test_slow_query_event_registration(self, clean_session_module):
        """Verify event listeners are registered."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///test.db"
        mock_settings.DB_SSL_MODE = "disable"
        mock_settings.is_production = False

        with (
            patch("app.shared.core.config.get_settings", return_value=mock_settings),
            patch("sqlalchemy.event.listens_for") as mock_listen,
            patch("sqlalchemy.ext.asyncio.create_async_engine"),
        ):
            importlib.reload(session_mod)
            assert mock_listen.called

    @pytest.mark.asyncio
    async def test_get_db_rls_postgres_path(self):
        """Test get_db path for PostgreSQL RLS."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = MagicMock()
        mock_session.bind.url.__str__.return_value = "postgresql+asyncpg://..."

        mock_request = MagicMock()
        mock_request.state.tenant_id = uuid4()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        mock_session_maker.return_value.__aexit__.return_value = None

        with patch("app.shared.db.session.async_session_maker", mock_session_maker):
            async for s in session_mod.get_db(mock_request):
                assert s == mock_session
                mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_set_session_tenant_id_postgres(self):
        """Test set_session_tenant_id for PostgreSQL."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = MagicMock()
        mock_session.bind.url.__str__.return_value = "postgresql+asyncpg://..."

        await session_mod.set_session_tenant_id(mock_session, uuid4())
        mock_session.execute.assert_called()

    def test_check_rls_policy_violation(self, clean_session_module):
        """Test check_rls_policy detecting missing context."""
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql+asyncpg://h/d"
        mock_settings.TESTING = False
        mock_settings.DB_SSL_MODE = "disable"
        mock_settings.is_production = False

        # Patch globally via reload to ensure check_rls_policy uses our settings
        # Use pass-through for listens_for to avoid registration errors but keep function
        with (
            patch("app.shared.core.config.get_settings", return_value=mock_settings),
            patch("sqlalchemy.ext.asyncio.create_async_engine"),
            patch(
                "sqlalchemy.event.listens_for",
                side_effect=lambda *args, **kwargs: lambda f: f,
            ),
        ):
            importlib.reload(session_mod)

            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}

            with pytest.raises(ValdrixException, match="RLS context missing"):
                session_mod.check_rls_policy(
                    mock_conn, None, "SELECT * FROM sensitive_data", {}, None, False
                )

    def test_check_rls_policy_exempt_and_system(self, clean_session_module):
        """Test bypass for exempt tables and system queries."""
        mock_conn = MagicMock()
        mock_conn.info = {"rls_context_set": False}

        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False

            # Internal execution (True) checks should pass
            session_mod.check_rls_policy(mock_conn, None, "SELECT 1", {}, None, True)

            # Simple SELECT 1 should pass
            session_mod.check_rls_policy(mock_conn, None, "SELECT 1", {}, None, False)

            # Exempt table - PATCH THE CONSTANTS MODULE where it is imported from
            with patch("app.shared.core.constants.RLS_EXEMPT_TABLES", ["audit_logs"]):
                session_mod.check_rls_policy(
                    mock_conn, None, "SELECT * FROM audit_logs", {}, None, False
                )

    def test_slow_query_logging(self, clean_session_module):
        """Trigger slow query logging branch."""
        mock_conn = MagicMock()
        start_time = time.perf_counter() - 2.0
        mock_conn.info = {"query_start_time": [start_time]}

        with patch("app.shared.db.session.logger") as mock_logger:
            # We also need to patch SLOW_QUERY_THRESHOLD_SECONDS slightly to ensure trigger
            with patch("app.shared.db.session.SLOW_QUERY_THRESHOLD_SECONDS", 0.1):
                session_mod.after_cursor_execute(
                    mock_conn, None, "SELECT *", {}, None, False
                )
                mock_logger.warning.assert_called()
