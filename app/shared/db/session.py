import ssl
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Dict, cast
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool, NullPool
from app.shared.core.config import get_settings
import structlog
import sys
import time
from fastapi import Request
from app.shared.core.exceptions import ValdrixException
from app.shared.core.ops_metrics import RLS_CONTEXT_MISSING, RLS_ENFORCEMENT_LATENCY

logger = structlog.get_logger()
settings = get_settings()

# Ensure ORM mappings are registered for scripts/workers that import the DB layer
# without importing `app/main.py`.
import app.models  # noqa: F401, E402

# Item 6: Critical Startup Error Handling
if not settings.DATABASE_URL and not settings.TESTING:
    logger.critical(
        "startup_failed_missing_db_url",
        msg="DATABASE_URL is not set. The application cannot start.",
    )
    sys.exit(1)
elif not settings.DATABASE_URL:
    # During testing, we can lazily allow missing URL if it's swapped later
    logger.debug("missing_db_url_in_testing_ignoring")

# Ensure DATABASE_URL is a string before string comparison
db_url = settings.DATABASE_URL or ""

# Fix missing async driver in PostgreSQL URLs (common with Supabase/Neon copy-paste)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# SSL Context: Configurable SSL modes for different environments
# Options: disable, require, verify-ca, verify-full
ssl_mode = settings.DB_SSL_MODE.lower()
connect_args: dict[str, Any] = {}

# Determine the actual URL to use. If testing, default to in-memory sqlite to avoid side-effects.
# Determine the actual URL to use.
# Default to in-memory sqlite in testing ONLY IF no explicit DATABASE_URL is provided,
# OR if the provided URL is not sqlite and we want to prevent side-effects on real DBs
# (unless explicitly allowed via a flag if we had one, but let's keep it safe for now).
effective_url = db_url
if settings.TESTING and not db_url:
    effective_url = "sqlite+aiosqlite:///:memory:"
elif (
    settings.TESTING and "sqlite" not in db_url and not settings.ALLOW_TEST_DATABASE_URL
):
    # Safety feature: swap non-sqlite to memory in testing to prevent accidental wipes.
    # To test against real Postgres, you must use a sqlite URL or handle it elsewhere.
    effective_url = "sqlite+aiosqlite:///:memory:"

# Determine if we're using sqlite (for pool and connection settings)
# Derived from effective_url to ensure testing overrides are caught
is_sqlite = "sqlite" in effective_url

if "postgresql" in effective_url:
    connect_args["statement_cache_size"] = 0  # Required for Supavisor

if ssl_mode == "disable":
    # WARNING: Only for local development with no SSL
    logger.warning(
        "database_ssl_disabled",
        msg="SSL disabled - INSECURE, do not use in production!",
    )
    if "postgresql" in effective_url:
        connect_args["ssl"] = False


elif ssl_mode == "require":
    # Item 2: Secure by Default - Try to use CA cert even in require mode if available
    ssl_context = ssl.create_default_context()
    if settings.DB_SSL_CA_CERT_PATH:
        ssl_context.load_verify_locations(cafile=settings.DB_SSL_CA_CERT_PATH)
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        logger.info(
            "database_ssl_require_verified", ca_cert=settings.DB_SSL_CA_CERT_PATH
        )
    elif settings.is_production:
        # Item 2: Prevent INSECURE FALLBACK in Production
        logger.critical(
            "database_ssl_require_failed_production",
            msg="SSL CA verification is REQUIRED in production/staging.",
        )
        raise ValueError(
            "DB_SSL_CA_CERT_PATH is mandatory when DB_SSL_MODE=require in production."
        )
    else:
        # Fallback to no verification only in local/dev
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        logger.warning(
            "database_ssl_require_insecure",
            msg="SSL enabled but CA verification skipped. MitM risk!",
        )
    if "postgresql" in effective_url:
        connect_args["ssl"] = ssl_context


elif ssl_mode in ("verify-ca", "verify-full"):
    if not settings.DB_SSL_CA_CERT_PATH:
        raise ValueError(f"DB_SSL_CA_CERT_PATH required for ssl_mode={ssl_mode}")
    ssl_context = ssl.create_default_context(cafile=settings.DB_SSL_CA_CERT_PATH)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = ssl_mode == "verify-full"
    if "postgresql" in effective_url:
        connect_args["ssl"] = ssl_context
    logger.info(
        "database_ssl_verified", mode=ssl_mode, ca_cert=settings.DB_SSL_CA_CERT_PATH
    )


else:
    raise ValueError(
        f"Invalid DB_SSL_MODE: {ssl_mode}. Use: disable, require, verify-ca, verify-full"
    )

# Engine: The connection pool manager
# - echo: Logs SQL queries when DEBUG=True (disable in production for performance)
# - pool_size: Number of persistent connections (10 for 10K+ user scaling)
# - max_overflow: Extra connections allowed during traffic spikes (20 for burst handling)
# - pool_pre_ping: Checks if connection is alive before using (prevents stale connections)
# - pool_recycle: Recycle connections after 5 min (Supavisor/Neon compatibility)
# Pool Configuration: Use NullPool for testing to avoid connection leaks across loops
POOL_CONFIG: dict[str, Any] = {
    "pool_recycle": settings.DB_POOL_RECYCLE,
    "pool_pre_ping": True,  # Health check connections before use
    "echo": settings.DB_ECHO,
}

if is_sqlite:
    POOL_CONFIG["poolclass"] = StaticPool
else:
    POOL_CONFIG["poolclass"] = NullPool

# Test-specific configuration
if settings.TESTING:
    if not is_sqlite:
        POOL_CONFIG.update(
            {
                "pool_size": 2,
                "max_overflow": 2,
            }
        )
    POOL_CONFIG["pool_recycle"] = 60  # Shorter recycle for tests

engine = create_async_engine(
    effective_url,
    **POOL_CONFIG,
    connect_args=connect_args,
)

SLOW_QUERY_THRESHOLD_SECONDS = 0.2


@event.listens_for(engine.sync_engine, "before_cursor_execute")
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


@event.listens_for(engine.sync_engine, "after_cursor_execute")
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
    if total > SLOW_QUERY_THRESHOLD_SECONDS:
        logger.warning(
            "slow_query_detected",
            duration_seconds=round(total, 3),
            statement=statement[:200] + "..." if len(statement) > 200 else statement,
            parameters=str(parameters)[:100] if parameters else None,
        )


# Session Factory: Creates new database sessions
# - expire_on_commit=False: Prevents lazy loading issues in async code
#   (objects remain accessible after commit without re-querying)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _session_uses_postgresql(session: AsyncSession) -> bool:
    """Best-effort dialect detection that works for real sessions and test doubles."""
    try:
        bind = getattr(session, "bind", None)
        bind_url = str(getattr(bind, "url", "")) if bind is not None else ""
        if bind_url:
            return "postgresql" in bind_url
    except Exception as e:
        logger.debug("session_dialect_detection_failed", error=str(e), exc_info=True)
    return "postgresql" in effective_url


async def get_db(
    request: Request = cast(Request, None),
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session with RLS context.
    """
    async with async_session_maker() as session:
        rls_context_set = False

        if request is not None:
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id:
                try:
                    # RLS: Only execute on PostgreSQL
                    if _session_uses_postgresql(session):
                        rls_start = time.perf_counter()
                        await session.execute(
                            text(
                                "SELECT set_config('app.current_tenant_id', :tid, true)"
                            ),
                            {"tid": str(tenant_id)},
                        )
                        RLS_ENFORCEMENT_LATENCY.observe(time.perf_counter() - rls_start)
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


async def get_system_db() -> AsyncGenerator[AsyncSession, None]:
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


async def set_session_tenant_id(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """
    Sets the RLS tenant context for the given session.
    Must be called after the tenant_id is known (e.g., in auth dependency).
    """
    session.info["rls_context_set"] = True

    # We must ensure the connection itself has the info, as listeners look there
    conn = await session.connection()
    conn.info["rls_context_set"] = True

    # For Postgres, execute the actual set_config for RLS
    if _session_uses_postgresql(session):
        try:
            rls_start = time.perf_counter()
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            RLS_ENFORCEMENT_LATENCY.observe(time.perf_counter() - rls_start)
        except Exception as e:
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

    # Skip internal/system queries or migrations
    from app.shared.core.constants import RLS_EXEMPT_TABLES

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

    for table in RLS_EXEMPT_TABLES:
        if (
            f"from {table}" in stmt_lower
            or f"into {table}" in stmt_lower
            or f"update {table}" in stmt_lower
        ):
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
            statement=statement[:200],
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
        async with async_session_maker() as session:
            # Item 4: Fast Health Check (No heavy joins/locks)
            await session.execute(text("SELECT 1"))

        latency = (time.perf_counter() - start_time) * 1000
        return {
            "status": "up",
            "latency_ms": round(latency, 2),
            "engine": engine.dialect.name if hasattr(engine, "dialect") else "unknown",
        }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "status": "down",
            "error": str(e),
            "latency_ms": (time.perf_counter() - start_time) * 1000,
        }
