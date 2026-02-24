import ssl
import time
import uuid
from dataclasses import dataclass
import inspect
import re
from threading import Lock
from typing import Any, AsyncGenerator, Dict, Optional, cast
from uuid import UUID

import structlog
from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.shared.core.config import get_settings
from app.shared.core.constants import RLS_EXEMPT_TABLES
from app.shared.core.exceptions import ValdrixException
from app.shared.core.ops_metrics import RLS_CONTEXT_MISSING, RLS_ENFORCEMENT_LATENCY

logger = structlog.get_logger()

# Ensure ORM mappings are registered for scripts/workers that import the DB layer
# without importing `app/main.py`.
import app.models  # noqa: F401, E402

settings = get_settings()

_RLS_EXEMPT_TABLE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(table.lower()) for table in RLS_EXEMPT_TABLES) + r")\b"
)


@dataclass(slots=True)
class _DBRuntime:
    settings: Any
    engine: AsyncEngine
    session_maker: async_sessionmaker[AsyncSession]
    effective_url: str


_db_runtime: _DBRuntime | None = None
_db_runtime_lock = Lock()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _normalize_db_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _resolve_effective_url(settings_obj: Any) -> tuple[str, bool, bool]:
    db_url = _normalize_db_url(str(getattr(settings_obj, "DATABASE_URL", "") or ""))
    allow_test_database_url = _as_bool(
        getattr(settings_obj, "ALLOW_TEST_DATABASE_URL", False)
    )
    use_null_pool = _as_bool(getattr(settings_obj, "DB_USE_NULL_POOL", False))
    external_pooler = _as_bool(getattr(settings_obj, "DB_EXTERNAL_POOLER", False))

    effective_url = db_url
    is_testing = bool(getattr(settings_obj, "TESTING", False))
    if is_testing and not db_url:
        effective_url = "sqlite+aiosqlite:///:memory:"
    elif is_testing and "sqlite" not in db_url and not allow_test_database_url:
        # Safety: protect tests from accidental writes to real databases.
        effective_url = "sqlite+aiosqlite:///:memory:"

    return effective_url, use_null_pool, external_pooler


def _build_connect_args(settings_obj: Any, effective_url: str) -> dict[str, Any]:
    connect_args: dict[str, Any] = {}
    ssl_mode = str(getattr(settings_obj, "DB_SSL_MODE", "require")).lower()

    if "postgresql" in effective_url:
        connect_args["statement_cache_size"] = 0  # Required for Supavisor

    if ssl_mode == "disable":
        logger.warning(
            "database_ssl_disabled",
            msg="SSL disabled - INSECURE, do not use in production!",
        )
        if "postgresql" in effective_url:
            connect_args["ssl"] = False
        return connect_args

    if ssl_mode == "require":
        ssl_context = ssl.create_default_context()
        if getattr(settings_obj, "DB_SSL_CA_CERT_PATH", None):
            ssl_context.load_verify_locations(cafile=settings_obj.DB_SSL_CA_CERT_PATH)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            logger.info(
                "database_ssl_require_verified",
                ca_cert=settings_obj.DB_SSL_CA_CERT_PATH,
            )
        elif bool(getattr(settings_obj, "is_production", False)):
            logger.critical(
                "database_ssl_require_failed_production",
                msg="SSL CA verification is REQUIRED in production/staging.",
            )
            raise ValueError(
                "DB_SSL_CA_CERT_PATH is mandatory when DB_SSL_MODE=require in production."
            )
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            logger.warning(
                "database_ssl_require_insecure",
                msg="SSL enabled but CA verification skipped. MitM risk!",
            )
        if "postgresql" in effective_url:
            connect_args["ssl"] = ssl_context
        return connect_args

    if ssl_mode in {"verify-ca", "verify-full"}:
        ca_cert = getattr(settings_obj, "DB_SSL_CA_CERT_PATH", None)
        if not ca_cert:
            raise ValueError(f"DB_SSL_CA_CERT_PATH required for ssl_mode={ssl_mode}")
        ssl_context = ssl.create_default_context(cafile=ca_cert)
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.check_hostname = ssl_mode == "verify-full"
        if "postgresql" in effective_url:
            connect_args["ssl"] = ssl_context
        logger.info("database_ssl_verified", mode=ssl_mode, ca_cert=ca_cert)
        return connect_args

    raise ValueError(
        f"Invalid DB_SSL_MODE: {ssl_mode}. Use: disable, require, verify-ca, verify-full"
    )


def _build_pool_config(
    settings_obj: Any, effective_url: str, use_null_pool: bool, external_pooler: bool
) -> dict[str, Any]:
    is_sqlite = "sqlite" in effective_url
    pool_config: dict[str, Any] = {
        "pool_recycle": getattr(settings_obj, "DB_POOL_RECYCLE", 3600),
        "pool_pre_ping": True,
        "echo": bool(getattr(settings_obj, "DB_ECHO", False)),
    }

    if is_sqlite:
        pool_config["poolclass"] = StaticPool
    elif use_null_pool:
        pool_config["poolclass"] = NullPool
        logger.warning(
            "database_null_pool_enabled",
            msg="NullPool enabled for external DB pooler mode.",
            external_pooler=external_pooler,
        )
    else:
        pool_config.update(
            {
                "pool_size": int(getattr(settings_obj, "DB_POOL_SIZE", 20)),
                "max_overflow": int(getattr(settings_obj, "DB_MAX_OVERFLOW", 10)),
                "pool_timeout": int(getattr(settings_obj, "DB_POOL_TIMEOUT", 30)),
            }
        )

    if bool(getattr(settings_obj, "TESTING", False)):
        if not is_sqlite and not use_null_pool:
            pool_config.update({"pool_size": 2, "max_overflow": 2, "pool_timeout": 5})
        pool_config["pool_recycle"] = 60

    return pool_config


def _register_engine_event_listeners(engine: AsyncEngine) -> None:
    sync_engine = getattr(engine, "sync_engine", None)
    # Test doubles/mocks may not support SQLAlchemy event registration.
    if sync_engine is None or type(sync_engine).__module__.startswith("unittest.mock"):
        logger.debug("db_engine_listener_registration_skipped_non_engine_target")
        return
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)


def _build_db_runtime() -> _DBRuntime:
    settings_obj = get_settings()
    db_url = str(getattr(settings_obj, "DATABASE_URL", "") or "").strip()
    if not db_url and not bool(getattr(settings_obj, "TESTING", False)):
        raise ValueError("DATABASE_URL is not set. The application cannot start.")
    if not db_url:
        logger.debug("missing_db_url_in_testing_ignoring")

    effective_url, use_null_pool, external_pooler = _resolve_effective_url(settings_obj)
    connect_args = _build_connect_args(settings_obj, effective_url)
    pool_config = _build_pool_config(
        settings_obj, effective_url, use_null_pool, external_pooler
    )
    engine = create_async_engine(
        effective_url,
        **pool_config,
        connect_args=connect_args,
    )
    _register_engine_event_listeners(engine)
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _DBRuntime(
        settings=settings_obj,
        engine=engine,
        session_maker=session_maker,
        effective_url=effective_url,
    )


def _get_db_runtime() -> _DBRuntime:
    global _db_runtime
    runtime = _db_runtime
    if runtime is not None:
        return runtime
    with _db_runtime_lock:
        runtime = _db_runtime
        if runtime is None:
            runtime = _build_db_runtime()
            _db_runtime = runtime
    return runtime


def reset_db_runtime() -> None:
    """Test helper for forcing runtime re-initialization on next access."""
    global _db_runtime
    runtime = _db_runtime
    _db_runtime = None

    if runtime is None:
        return

    try:
        # Use sync disposal so reset can be called from non-async test fixtures.
        runtime.engine.sync_engine.dispose()
    except Exception as exc:
        logger.debug("db_runtime_dispose_skipped", error=str(exc), exc_info=True)


def get_engine() -> AsyncEngine:
    """Return the active async engine."""
    return _get_db_runtime().engine


def async_session_maker(*args: Any, **kwargs: Any) -> Any:
    """Return a new async session from the active session factory."""
    return _get_db_runtime().session_maker(*args, **kwargs)


def _get_slow_query_threshold_seconds() -> float:
    """Return configurable slow-query threshold with a safe fallback."""
    try:
        threshold = float(getattr(settings, "DB_SLOW_QUERY_THRESHOLD_SECONDS", 0.2))
    except (TypeError, ValueError):
        threshold = 0.2
    return threshold if threshold > 0 else 0.2


def before_cursor_execute(
    conn: Connection,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    _context: Any,
    _executemany: bool,
) -> None:
    """Record query start time."""
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


def after_cursor_execute(
    conn: Connection,
    _cursor: Any,
    statement: str,
    parameters: Any,
    _context: Any,
    _executemany: bool,
) -> None:
    """Log slow queries."""
    total = time.perf_counter() - conn.info["query_start_time"].pop(-1)
    threshold = _get_slow_query_threshold_seconds()
    if total > threshold:
        logger.warning(
            "slow_query_detected",
            duration_seconds=round(total, 3),
            threshold_seconds=threshold,
            statement=statement[:200] + "..." if len(statement) > 200 else statement,
            parameters=str(parameters)[:100] if parameters else None,
        )


def _session_uses_postgresql(session: AsyncSession) -> bool:
    backend, source = _resolve_session_backend(session)
    if backend == "unknown":
        logger.warning(
            "session_dialect_unknown",
            source=source,
            fail_safe_default=False,
        )
        return False
    return backend == "postgresql"


def _backend_from_url(url: str) -> Optional[str]:
    value = url.strip().lower()
    if not value:
        return None
    if "postgresql" in value:
        return "postgresql"
    if "sqlite" in value:
        return "sqlite"
    if "mysql" in value:
        return "mysql"
    return None


def _resolve_session_backend(session: AsyncSession) -> tuple[str, str]:
    """
    Resolve effective DB backend for a session with explicit source metadata.
    Returns `(backend, source)` where backend is one of:
    - `postgresql`, `sqlite`, `mysql`
    - `unknown` (unresolved)

    Resolution order:
    1) `session.bind.dialect.name`
    2) `session.bind.url`
    3) `session.get_bind()` dialect/url
    4) module-level configured URL fallback (`effective_url`)
    """
    try:
        bind = getattr(session, "bind", None)
        if bind is not None:
            dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
            if isinstance(dialect_name, str) and dialect_name.strip():
                return dialect_name.strip().lower(), "session.bind.dialect.name"

            bind_url = getattr(bind, "url", None)
            if bind_url is not None:
                backend = _backend_from_url(str(bind_url))
                if backend is not None:
                    return backend, "session.bind.url"
    except Exception as e:
        logger.debug("session_bind_introspection_failed", error=str(e), exc_info=True)

    try:
        get_bind = getattr(session, "get_bind", None)
        runtime_bind = None
        if callable(get_bind):
            if inspect.iscoroutinefunction(get_bind):
                logger.debug("session_get_bind_is_coroutine_skipped")
            else:
                runtime_bind = get_bind()
        if runtime_bind is not None:
            dialect_name = getattr(getattr(runtime_bind, "dialect", None), "name", None)
            if isinstance(dialect_name, str) and dialect_name.strip():
                return dialect_name.strip().lower(), "session.get_bind().dialect.name"

            runtime_url = getattr(runtime_bind, "url", None)
            if runtime_url is not None:
                backend = _backend_from_url(str(runtime_url))
                if backend is not None:
                    return backend, "session.get_bind().url"
    except Exception as e:
        logger.debug("session_runtime_bind_resolution_failed", error=str(e), exc_info=True)

    fallback_url, _, _ = _resolve_effective_url(get_settings())
    fallback_backend = _backend_from_url(fallback_url)
    if fallback_backend is not None:
        logger.warning(
            "session_dialect_fallback_used",
            backend=fallback_backend,
            source="configured_effective_url",
        )
        return fallback_backend, "configured_effective_url"

    return "unknown", "unresolved"


async def _get_db_impl(
    request: Request = cast(Request, None),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Internal implementation for FastAPI DB dependency.

    Wrapped by `get_db` to keep dependency callable identity stable across
    module reloads (critical for dependency overrides).
    """
    async with async_session_maker() as session:
        rls_context_set = False

        if request is not None:
            tenant_id = getattr(request.state, "tenant_id", None)
            tenant_key = str(tenant_id) if isinstance(tenant_id, uuid.UUID) else tenant_id
            if tenant_id:
                try:
                    backend, source = _resolve_session_backend(session)
                    # RLS: execute set_config only on PostgreSQL.
                    if backend == "postgresql":
                        rls_start = time.perf_counter()
                        await session.execute(
                            text(
                                "SELECT set_config('app.current_tenant_id', :tid, true)"
                            ),
                            {"tid": str(tenant_id)},
                        )
                        RLS_ENFORCEMENT_LATENCY.observe(time.perf_counter() - rls_start)
                        rls_context_set = True
                    elif backend == "unknown":
                        # Fail closed: do not mark context as set when backend cannot be resolved.
                        logger.error(
                            "rls_session_backend_unknown_fail_closed",
                            source=source,
                            tenant_id=tenant_key,
                        )
                        rls_context_set = False
                    else:
                        # Non-Postgres backend (e.g. sqlite in tests).
                        rls_context_set = True

                except Exception as e:
                    logger.warning("rls_context_set_failed", error=str(e))
        else:
            # For system tasks or background jobs not triggered by a request,
            # we assume the handler will set its own context if needed,
            # or it's a system-level operation.
            rls_context_set = True

        # PROPAGATION: Ensure the listener can see the RLS status on the connection
        # and satisfy session-level checks in existing tests.
        session.info["rls_context_set"] = rls_context_set

        conn = await session.connection()
        conn.info["rls_context_set"] = rls_context_set

        try:
            yield session
        finally:
            await session.close()


_get_db_impl_ref = _get_db_impl
if "get_db" not in globals():

    async def get_db(
        request: Request = cast(Request, None),
    ) -> AsyncGenerator[AsyncSession, None]:
        async for session in _get_db_impl_ref(request):
            yield session


async def _get_system_db_impl() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a DB session for system/public operations that must not require a tenant context.

    This intentionally sets `rls_context_set=None` so the RLS enforcement listener does not
    block execution (it only blocks when the flag is explicitly False).

    IMPORTANT:
    - Only use this for tables that are NOT tenant-scoped or that intentionally expose
      a public mapping (for example, SSO domain routing lookup).
    - Do not use this for tenant-scoped business data.
    """
    async with async_session_maker() as session:
        session.info["rls_context_set"] = None
        conn = await session.connection()
        conn.info["rls_context_set"] = None
        try:
            yield session
        finally:
            await session.close()


_get_system_db_impl_ref = _get_system_db_impl
if "get_system_db" not in globals():

    async def get_system_db() -> AsyncGenerator[AsyncSession, None]:
        async for session in _get_system_db_impl_ref():
            yield session


async def set_session_tenant_id(session: AsyncSession, tenant_id: Optional[UUID]) -> None:
    """Sets the tenant_id in the database session's info dictionary."""
    session.info["tenant_id"] = tenant_id

    # We must ensure the connection itself has the info, as listeners look there
    conn = await session.connection()
    backend, source = _resolve_session_backend(session)
    if backend == "unknown":
        # Fail closed on unresolved backend detection.
        session.info["rls_context_set"] = False
        conn.info["rls_context_set"] = False
        logger.error(
            "set_session_tenant_id_backend_unknown_fail_closed",
            source=source,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
        return

    # Mark context as set for known backends.
    session.info["rls_context_set"] = True
    conn.info["rls_context_set"] = True

    # For Postgres, execute the actual set_config for RLS.
    if backend == "postgresql":
        try:
            rls_start = time.perf_counter()
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            RLS_ENFORCEMENT_LATENCY.observe(time.perf_counter() - rls_start)
        except Exception as e:
            session.info["rls_context_set"] = False
            conn.info["rls_context_set"] = False
            logger.warning("failed_to_set_rls_config_in_session", error=str(e))


@event.listens_for(Engine, "before_cursor_execute", retval=True)
def check_rls_policy(
    conn: Connection,
    _cursor: Any,
    statement: str,
    parameters: Any,
    _context: Any,
    _executemany: bool,
) -> tuple[str, Any]:
    """
    PRODUCTION: Hardened Multi-Tenancy RLS Enforcement

    This listener ENFORCES Row-Level Security by raising an exception if a query runs
    without proper tenant context. This prevents accidental data leaks across tenants.
    """
    # Skip enforcement in tests to avoid dialect-specific transaction issues (e.g. prepare)
    if settings.TESTING and not settings.ENFORCE_RLS_IN_TESTS:
        return statement, parameters

    stmt_lower = statement.lower()

    # Only enforce for data-access statements. Transaction/session control statements
    # (BEGIN/COMMIT/ROLLBACK/SET/SHOW/...) must be allowed even when tenant context
    # is not yet established (e.g. during auth bootstrap).
    stmt_stripped = stmt_lower.lstrip()
    if stmt_stripped:
        verb = stmt_stripped.split(None, 1)[0]
        if verb not in {"select", "insert", "update", "delete", "with"}:
            return statement, parameters

    if (
        "select 1" in stmt_lower
        or "select version()" in stmt_lower
        or "select pg_is_in_recovery()" in stmt_lower
    ):
        return statement, parameters

    if _RLS_EXEMPT_TABLE_PATTERN.search(stmt_lower):
        return statement, parameters

    # Identify the state from the connection info
    rls_status = conn.info.get("rls_context_set")

    # PRODUCTION: Raise exception on RLS context missing (False)
    # Note: None is allowed for system/internal connections that don't go through get_db
    # but for all request-bound sessions, it will be True or False.
    if rls_status is False:
        try:
            if statement.split():
                RLS_CONTEXT_MISSING.labels(
                    statement_type=statement.split()[0].upper()
                ).inc()
        except Exception as e:
            logger.debug("rls_metric_increment_failed", error=str(e))

        logger.critical(
            "rls_enforcement_violation_detected",
            statement=statement[:500],
            rls_status=rls_status,
            error="Query executed WITHOUT tenant insulation set. RLS policy violated!",
        )

        # PRODUCTION: Hard exception - no execution allowed
        raise ValdrixException(
            message="RLS context missing - query execution aborted",
            code="rls_enforcement_failed",
            status_code=500,
            details={
                "reason": "Multi-tenant isolation enforcement failed",
                "action": "This is a critical security error. Check that all DB sessions are initialized with tenant context.",
            },
        )

    return statement, parameters


async def health_check() -> Dict[str, Any]:
    """Database health check for monitoring."""
    start_time = time.perf_counter()
    try:
        db_engine = get_engine()
        async with async_session_maker() as session:
            # Item 4: Fast Health Check (No heavy joins/locks)
            await session.execute(text("SELECT 1"))

        latency = (time.perf_counter() - start_time) * 1000
        return {
            "status": "up",
            "latency_ms": round(latency, 2),
            "engine": (
                db_engine.dialect.name if hasattr(db_engine, "dialect") else "unknown"
            ),
        }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "status": "down",
            "error": str(e),
            "latency_ms": (time.perf_counter() - start_time) * 1000,
        }
