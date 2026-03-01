from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.shared.db.session as session_mod
from app.shared.core.exceptions import ValdrixException


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    session_mod._db_runtime = None


class _DummyAsyncCM:
    def __init__(self, value: object):
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_bool_and_url_helpers() -> None:
    assert session_mod._as_bool(True) is True
    assert session_mod._as_bool(" YES ") is True
    assert session_mod._as_bool("no") is False
    assert session_mod._as_bool(1) is False

    assert session_mod._normalize_db_url("postgresql://h/db") == "postgresql+asyncpg://h/db"
    assert session_mod._normalize_db_url("sqlite:///x") == "sqlite:///x"


def test_resolve_effective_url_testing_safety_paths() -> None:
    settings_empty = SimpleNamespace(
        DATABASE_URL="",
        ALLOW_TEST_DATABASE_URL=False,
        DB_USE_NULL_POOL=False,
        DB_EXTERNAL_POOLER=False,
        TESTING=True,
    )
    effective, use_null, external = session_mod._resolve_effective_url(settings_empty)
    assert effective == "sqlite+aiosqlite:///:memory:"
    assert use_null is False and external is False

    settings_real = SimpleNamespace(
        DATABASE_URL="postgresql://prod/db",
        ALLOW_TEST_DATABASE_URL=False,
        DB_USE_NULL_POOL=True,
        DB_EXTERNAL_POOLER=True,
        TESTING=True,
    )
    effective2, use_null2, external2 = session_mod._resolve_effective_url(settings_real)
    assert effective2 == "sqlite+aiosqlite:///:memory:"
    assert use_null2 is True and external2 is True


@pytest.mark.parametrize("mode", ["verify-ca", "verify-full"])
def test_build_connect_args_verified_ssl_modes(mode: str) -> None:
    settings = SimpleNamespace(
        DB_SSL_MODE=mode,
        DB_SSL_CA_CERT_PATH="/tmp/ca.pem",
        is_production=False,
    )
    ssl_ctx = MagicMock()
    with patch("app.shared.db.session.ssl.create_default_context", return_value=ssl_ctx) as mock_create:
        args = session_mod._build_connect_args(settings, "postgresql+asyncpg://h/db")
    mock_create.assert_called_once_with(cafile="/tmp/ca.pem")
    assert args["ssl"] is ssl_ctx
    assert ssl_ctx.check_hostname is (mode == "verify-full")


def test_build_connect_args_verified_mode_non_postgres_skips_ssl_attach() -> None:
    settings = SimpleNamespace(
        DB_SSL_MODE="verify-ca",
        DB_SSL_CA_CERT_PATH="/tmp/ca.pem",
        is_production=False,
    )
    with patch("app.shared.db.session.ssl.create_default_context", return_value=MagicMock()):
        args = session_mod._build_connect_args(settings, "sqlite+aiosqlite:///:memory:")
    assert "ssl" not in args


def test_build_connect_args_require_branches_with_and_without_ca() -> None:
    ssl_ctx = MagicMock()
    settings_ca = SimpleNamespace(
        DB_SSL_MODE="require",
        DB_SSL_CA_CERT_PATH="/tmp/ca.pem",
        is_production=False,
    )
    with patch("app.shared.db.session.ssl.create_default_context", return_value=ssl_ctx):
        args = session_mod._build_connect_args(settings_ca, "postgresql+asyncpg://h/db")
    assert args["ssl"] is ssl_ctx
    ssl_ctx.load_verify_locations.assert_called_once_with(cafile="/tmp/ca.pem")

    ssl_ctx2 = MagicMock()
    settings_insecure = SimpleNamespace(
        DB_SSL_MODE="require",
        DB_SSL_CA_CERT_PATH=None,
        is_production=False,
    )
    with patch("app.shared.db.session.ssl.create_default_context", return_value=ssl_ctx2):
        args2 = session_mod._build_connect_args(settings_insecure, "postgresql+asyncpg://h/db")
    assert args2["ssl"] is ssl_ctx2
    assert ssl_ctx2.check_hostname is False
    assert ssl_ctx2.verify_mode == session_mod.ssl.CERT_NONE

    with patch("app.shared.db.session.ssl.create_default_context", return_value=MagicMock()):
        args3 = session_mod._build_connect_args(
            settings_insecure, "sqlite+aiosqlite:///:memory:"
        )
    assert "ssl" not in args3


def test_build_pool_config_null_pool_and_testing_override() -> None:
    settings = SimpleNamespace(DB_POOL_RECYCLE=123, DB_ECHO=False, TESTING=False)
    cfg = session_mod._build_pool_config(
        settings, "postgresql+asyncpg://h/db", use_null_pool=True, external_pooler=True
    )
    assert cfg["poolclass"] is session_mod.NullPool

    settings_testing = SimpleNamespace(
        DB_POOL_RECYCLE=3600,
        DB_ECHO=False,
        TESTING=True,
        DB_POOL_SIZE=20,
        DB_MAX_OVERFLOW=10,
        DB_POOL_TIMEOUT=30,
    )
    cfg_testing = session_mod._build_pool_config(
        settings_testing,
        "postgresql+asyncpg://h/db",
        use_null_pool=False,
        external_pooler=False,
    )
    assert cfg_testing["pool_size"] == 2
    assert cfg_testing["max_overflow"] == 2
    assert cfg_testing["pool_timeout"] == 5
    assert cfg_testing["pool_recycle"] == 60


def test_register_engine_event_listeners_real_target() -> None:
    class SyncEngine:
        pass

    engine = SimpleNamespace(sync_engine=SyncEngine())
    with patch("app.shared.db.session.event.listen") as mock_listen:
        session_mod._register_engine_event_listeners(engine)  # type: ignore[arg-type]

    assert mock_listen.call_count == 2


def test_build_db_runtime_testing_missing_db_url_and_wrappers() -> None:
    fake_engine = SimpleNamespace(sync_engine=SimpleNamespace(dispose=MagicMock()))
    fake_session_factory = MagicMock(return_value="session-instance")
    fake_runtime = session_mod._DBRuntime(
        settings=SimpleNamespace(),
        engine=fake_engine,
        session_maker=fake_session_factory,
        effective_url="sqlite+aiosqlite:///:memory:",
    )

    settings = SimpleNamespace(
        DATABASE_URL="",
        TESTING=True,
        DB_SSL_MODE="disable",
        is_production=False,
        DB_POOL_RECYCLE=60,
        DB_ECHO=False,
    )

    with (
        patch("app.shared.db.session.get_settings", return_value=settings),
        patch("app.shared.db.session.create_async_engine", return_value=fake_engine),
        patch("app.shared.db.session.async_sessionmaker", return_value=fake_session_factory),
        patch("app.shared.db.session._register_engine_event_listeners"),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        runtime = session_mod._build_db_runtime()

    assert runtime.engine is fake_engine
    mock_logger.debug.assert_any_call("missing_db_url_in_testing_ignoring")

    with patch("app.shared.db.session._get_db_runtime", return_value=fake_runtime):
        assert session_mod.get_engine() is fake_engine
        assert session_mod.async_session_maker("x", flag=True) == "session-instance"
        fake_session_factory.assert_called_once_with("x", flag=True)


def test_get_db_runtime_cached_and_set_inside_lock_paths() -> None:
    runtime_cached = SimpleNamespace(name="cached")
    session_mod._db_runtime = runtime_cached  # line 230 path
    assert session_mod._get_db_runtime() is runtime_cached

    runtime_inside_lock = SimpleNamespace(name="inside-lock")
    session_mod._db_runtime = None

    class FakeLock:
        def __enter__(self) -> None:
            session_mod._db_runtime = runtime_inside_lock
            return None

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    with patch.object(session_mod, "_db_runtime_lock", FakeLock()):
        assert session_mod._get_db_runtime() is runtime_inside_lock


def test_reset_db_runtime_dispose_exception_logged() -> None:
    dispose = MagicMock(side_effect=RuntimeError("dispose failed"))
    runtime = SimpleNamespace(engine=SimpleNamespace(sync_engine=SimpleNamespace(dispose=dispose)))
    session_mod._db_runtime = runtime

    with patch("app.shared.db.session.logger") as mock_logger:
        session_mod.reset_db_runtime()

    assert session_mod._db_runtime is None
    mock_logger.debug.assert_called_once()


def test_slow_query_threshold_and_after_cursor_execute_fast_path() -> None:
    with patch.object(session_mod, "settings", SimpleNamespace(DB_SLOW_QUERY_THRESHOLD_SECONDS="bad")):
        assert session_mod._get_slow_query_threshold_seconds() == 0.2
    with patch.object(session_mod, "settings", SimpleNamespace(DB_SLOW_QUERY_THRESHOLD_SECONDS=0)):
        assert session_mod._get_slow_query_threshold_seconds() == 0.2

    conn = MagicMock()
    conn.info = {"query_start_time": [session_mod.time.perf_counter()]}
    with (
        patch("app.shared.db.session._get_slow_query_threshold_seconds", return_value=10.0),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        session_mod.after_cursor_execute(conn, None, "SELECT 1", {}, None, False)
    mock_logger.warning.assert_not_called()


def test_backend_from_url_and_session_backend_resolution_branches() -> None:
    assert session_mod._backend_from_url("") is None
    assert session_mod._backend_from_url("mysql://h/db") == "mysql"

    session = MagicMock()
    session.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    backend, source = session_mod._resolve_session_backend(session)
    assert (backend, source) == ("postgresql", "session.bind.dialect.name")

    class BindRaises:
        @property
        def dialect(self) -> object:
            raise RuntimeError("bind introspection boom")

    session_exc = MagicMock()
    session_exc.bind = BindRaises()
    session_exc.get_bind = None
    with (
        patch("app.shared.db.session.logger") as mock_logger,
        patch("app.shared.db.session._resolve_effective_url", return_value=("", False, False)),
    ):
        backend2, source2 = session_mod._resolve_session_backend(session_exc)
    assert (backend2, source2) == ("unknown", "unresolved")
    mock_logger.debug.assert_called()

    session_bind_url_none = MagicMock()
    session_bind_url_none.bind = SimpleNamespace(dialect=SimpleNamespace(name=" "), url=None)
    runtime_bind = SimpleNamespace(url="mysql://runtime")
    session_bind_url_none.get_bind = MagicMock(return_value=runtime_bind)
    backend3, source3 = session_mod._resolve_session_backend(session_bind_url_none)
    assert (backend3, source3) == ("mysql", "session.get_bind().url")

    session_runtime_dialect = MagicMock()
    session_runtime_dialect.bind = None
    session_runtime_dialect.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    backend_runtime, source_runtime = session_mod._resolve_session_backend(
        session_runtime_dialect
    )
    assert (backend_runtime, source_runtime) == (
        "sqlite",
        "session.get_bind().dialect.name",
    )

    session_runtime_unknown_url = MagicMock()
    session_runtime_unknown_url.bind = None
    session_runtime_unknown_url.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name=" "), url="oracle://x")
    )
    with patch("app.shared.db.session._resolve_effective_url", return_value=("", False, False)):
        backend_unknown_url, source_unknown_url = session_mod._resolve_session_backend(
            session_runtime_unknown_url
        )
    assert (backend_unknown_url, source_unknown_url) == ("unknown", "unresolved")

    session_runtime_no_url = MagicMock()
    session_runtime_no_url.bind = None
    session_runtime_no_url.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name=" "), url=None)
    )
    with patch("app.shared.db.session._resolve_effective_url", return_value=("", False, False)):
        backend_no_url, source_no_url = session_mod._resolve_session_backend(
            session_runtime_no_url
        )
    assert (backend_no_url, source_no_url) == ("unknown", "unresolved")

    session_get_bind_raises = MagicMock()
    session_get_bind_raises.bind = None
    session_get_bind_raises.get_bind = MagicMock(side_effect=RuntimeError("get_bind boom"))
    with (
        patch("app.shared.db.session.logger") as mock_logger,
        patch("app.shared.db.session._resolve_effective_url", return_value=("", False, False)),
    ):
        backend4, source4 = session_mod._resolve_session_backend(session_get_bind_raises)
    assert (backend4, source4) == ("unknown", "unresolved")
    mock_logger.debug.assert_called()


def test_session_uses_postgresql_unknown_backend_logs_warning() -> None:
    with (
        patch("app.shared.db.session._resolve_session_backend", return_value=("unknown", "x")),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        assert session_mod._session_uses_postgresql(MagicMock()) is False
    mock_logger.warning.assert_called_once()

    with patch("app.shared.db.session._resolve_session_backend", return_value=("postgresql", "x")):
        assert session_mod._session_uses_postgresql(MagicMock()) is True


@pytest.mark.asyncio
async def test_get_db_impl_request_without_tenant_sets_false_and_closes() -> None:
    mock_session = MagicMock()
    mock_session.info = {}
    conn = MagicMock(info={})
    mock_session.connection = AsyncMock(return_value=conn)
    mock_session.close = AsyncMock()

    request = MagicMock()
    request.state.tenant_id = None

    with patch("app.shared.db.session.async_session_maker", return_value=_DummyAsyncCM(mock_session)):
        agen = session_mod._get_db_impl(request)
        yielded = await agen.__anext__()
        assert yielded is mock_session
        assert mock_session.info["rls_context_set"] is False
        assert mock_session.info["rls_system_context"] is False
        assert conn.info["rls_context_set"] is False
        assert conn.info["rls_system_context"] is False
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()


@pytest.mark.asyncio
async def test_get_system_db_impl_and_wrapper() -> None:
    mock_session = MagicMock()
    mock_session.info = {}
    conn = MagicMock(info={})
    mock_session.connection = AsyncMock(return_value=conn)
    mock_session.close = AsyncMock()

    with patch("app.shared.db.session.async_session_maker", return_value=_DummyAsyncCM(mock_session)):
        agen = session_mod._get_system_db_impl()
        yielded = await agen.__anext__()
        assert yielded is mock_session
        assert mock_session.info["rls_context_set"] is None
        assert mock_session.info["rls_system_context"] is True
        assert conn.info["rls_context_set"] is None
        assert conn.info["rls_system_context"] is True
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    async def _fake_system_gen():
        yield "sys-session"

    with patch.object(session_mod, "_get_system_db_impl", _fake_system_gen):
        values = []
        async for item in session_mod.get_system_db():
            values.append(item)
    assert values == ["sys-session"]


@pytest.mark.asyncio
async def test_set_session_tenant_id_postgres_execute_failure_marks_fail_closed() -> None:
    tenant_id = uuid4()
    conn = MagicMock(info={})
    session = MagicMock()
    session.info = {}
    session.connection = AsyncMock(return_value=conn)
    session.execute = AsyncMock(side_effect=RuntimeError("set_config failed"))

    with (
        patch("app.shared.db.session._resolve_session_backend", return_value=("postgresql", "bind")),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        await session_mod.set_session_tenant_id(session, tenant_id)

    assert session.info["rls_context_set"] is False
    assert session.info["rls_system_context"] is False
    assert conn.info["rls_context_set"] is False
    assert conn.info["rls_system_context"] is False
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_set_session_tenant_id_none_delegates_to_clear_context() -> None:
    session = MagicMock()
    session.info = {}

    clear_mock = AsyncMock()
    with patch.object(session_mod, "clear_session_tenant_context", clear_mock):
        await session_mod.set_session_tenant_id(session, None)

    clear_mock.assert_awaited_once_with(session)


@pytest.mark.asyncio
async def test_clear_session_tenant_context_postgres_fails_closed() -> None:
    conn = MagicMock(info={})
    session = MagicMock()
    session.info = {"tenant_id": "tenant-1", "rls_context_set": True}
    session.connection = AsyncMock(return_value=conn)
    session.execute = AsyncMock(return_value=None)

    with patch(
        "app.shared.db.session._resolve_session_backend",
        return_value=("postgresql", "bind"),
    ):
        await session_mod.clear_session_tenant_context(session)

    assert session.info["tenant_id"] is None
    assert session.info["rls_context_set"] is False
    assert session.info["rls_system_context"] is False
    assert conn.info["tenant_id"] is None
    assert conn.info["rls_context_set"] is False
    assert conn.info["rls_system_context"] is False
    session.execute.assert_awaited_once()
    sql_text = str(session.execute.await_args.args[0])
    assert "set_config('app.current_tenant_id', '', true)" in sql_text


@pytest.mark.asyncio
async def test_clear_session_tenant_context_postgres_clear_failure_logged() -> None:
    conn = MagicMock(info={})
    session = MagicMock()
    session.info = {}
    session.connection = AsyncMock(return_value=conn)
    session.execute = AsyncMock(side_effect=RuntimeError("clear failed"))

    with (
        patch(
            "app.shared.db.session._resolve_session_backend",
            return_value=("postgresql", "bind"),
        ),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        await session_mod.clear_session_tenant_context(session)

    assert session.info["rls_context_set"] is False
    assert conn.info["rls_context_set"] is False
    mock_logger.warning.assert_called_once()


def test_check_rls_policy_additional_branch_paths() -> None:
    conn = MagicMock()
    conn.info = {"rls_context_set": True}

    with patch.object(session_mod, "settings", SimpleNamespace(TESTING=True, ENFORCE_RLS_IN_TESTS=False)):
        stmt, params = session_mod.check_rls_policy(conn, None, "SELECT * FROM x", {}, None, False)
        assert stmt == "SELECT * FROM x"
        assert params == {}

    with patch.object(session_mod, "settings", SimpleNamespace(TESTING=False, ENFORCE_RLS_IN_TESTS=True)):
        stmt2, _ = session_mod.check_rls_policy(conn, None, "BEGIN", {}, None, False)
        assert stmt2 == "BEGIN"
        stmt3, _ = session_mod.check_rls_policy(conn, None, "SELECT * FROM t", {}, None, False)
        assert stmt3 == "SELECT * FROM t"

    conn_false = MagicMock()
    conn_false.info = {"rls_context_set": False}
    with patch.object(session_mod, "settings", SimpleNamespace(TESTING=False, ENFORCE_RLS_IN_TESTS=True)):
        with pytest.raises(ValdrixException):
            session_mod.check_rls_policy(conn_false, None, "   ", {}, None, False)

    with (
        patch.object(session_mod, "settings", SimpleNamespace(TESTING=False, ENFORCE_RLS_IN_TESTS=True)),
        patch.object(session_mod, "RLS_CONTEXT_MISSING") as mock_metric,
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        mock_metric.labels.side_effect = RuntimeError("metric failed")
        with pytest.raises(ValdrixException):
            session_mod.check_rls_policy(conn_false, None, "SELECT * FROM z", {}, None, False)
    mock_logger.debug.assert_any_call("rls_metric_increment_failed", error="metric failed")

    conn_ambiguous = MagicMock()
    conn_ambiguous.info = {"rls_context_set": None}
    with patch.object(
        session_mod,
        "settings",
        SimpleNamespace(TESTING=False, ENFORCE_RLS_IN_TESTS=True),
    ):
        with pytest.raises(ValdrixException):
            session_mod.check_rls_policy(
                conn_ambiguous, None, "SELECT * FROM accounts", {}, None, False
            )

    conn_system = MagicMock()
    conn_system.info = {"rls_context_set": None, "rls_system_context": True}
    with patch.object(
        session_mod,
        "settings",
        SimpleNamespace(TESTING=False, ENFORCE_RLS_IN_TESTS=True),
    ):
        stmt_system, _ = session_mod.check_rls_policy(
            conn_system, None, "SELECT * FROM exchange_rates", {}, None, False
        )
        assert stmt_system == "SELECT * FROM exchange_rates"


@pytest.mark.asyncio
async def test_health_check_success_and_error_paths() -> None:
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=None)

    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    with (
        patch("app.shared.db.session.get_engine", return_value=engine),
        patch("app.shared.db.session.async_session_maker", return_value=_DummyAsyncCM(mock_session)),
    ):
        ok = await session_mod.health_check()
    assert ok["status"] == "up"
    assert ok["engine"] == "postgresql"

    with (
        patch("app.shared.db.session.get_engine", side_effect=RuntimeError("db down")),
        patch("app.shared.db.session.logger") as mock_logger,
    ):
        down = await session_mod.health_check()
    assert down["status"] == "down"
    assert "db down" in down["error"]
    mock_logger.error.assert_called_once()
