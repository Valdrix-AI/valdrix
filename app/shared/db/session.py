import ssl
import uuid
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from app.shared.core.config import get_settings
import structlog
import sys
import time
from fastapi import Request
from sqlalchemy.pool import StaticPool, NullPool
from app.shared.core.exceptions import ValdrixException
from app.shared.core.ops_metrics import RLS_CONTEXT_MISSING

logger = structlog.get_logger()
settings = get_settings()

# Item 6: Critical Startup Error Handling
if not settings.DATABASE_URL:
    logger.critical("startup_failed_missing_db_url", 
                   msg="DATABASE_URL is not set. The application cannot start.")
    sys.exit(1)

# SSL Context: Configurable SSL modes for different environments
# Options: disable, require, verify-ca, verify-full
ssl_mode = settings.DB_SSL_MODE.lower()
connect_args = {}
if "postgresql" in settings.DATABASE_URL:
    connect_args["statement_cache_size"] = 0  # Required for Supavisor

if ssl_mode == "disable":
    # WARNING: Only for local development with no SSL
    logger.warning("database_ssl_disabled",
                   msg="SSL disabled - INSECURE, do not use in production!")
    if "postgresql" in settings.DATABASE_URL:
        connect_args["ssl"] = False


elif ssl_mode == "require":
    # Item 2: Secure by Default - Try to use CA cert even in require mode if available
    ssl_context = ssl.create_default_context()
    if settings.DB_SSL_CA_CERT_PATH:
        ssl_context.load_verify_locations(cafile=settings.DB_SSL_CA_CERT_PATH)
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        logger.info("database_ssl_require_verified", ca_cert=settings.DB_SSL_CA_CERT_PATH)
    elif settings.is_production:
        # Item 2: Prevent INSECURE FALLBACK in Production
        logger.critical("database_ssl_require_failed_production",
                        msg="SSL CA verification is REQUIRED in production/staging.")
        raise ValueError("DB_SSL_CA_CERT_PATH is mandatory when DB_SSL_MODE=require in production.")
    else:
        # Fallback to no verification only in local/dev
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        logger.warning("database_ssl_require_insecure", 
                       msg="SSL enabled but CA verification skipped. MitM risk!")
    if "postgresql" in settings.DATABASE_URL:
        connect_args["ssl"] = ssl_context


elif ssl_mode in ("verify-ca", "verify-full"):
    if not settings.DB_SSL_CA_CERT_PATH:
        raise ValueError(f"DB_SSL_CA_CERT_PATH required for ssl_mode={ssl_mode}")
    ssl_context = ssl.create_default_context(cafile=settings.DB_SSL_CA_CERT_PATH)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = (ssl_mode == "verify-full")
    if "postgresql" in settings.DATABASE_URL:
        connect_args["ssl"] = ssl_context
    logger.info("database_ssl_verified", mode=ssl_mode, ca_cert=settings.DB_SSL_CA_CERT_PATH)


else:
    raise ValueError(f"Invalid DB_SSL_MODE: {ssl_mode}. Use: disable, require, verify-ca, verify-full")

# Engine: The connection pool manager
# - echo: Logs SQL queries when DEBUG=True (disable in production for performance)
# - pool_size: Number of persistent connections (10 for 10K+ user scaling)
# - max_overflow: Extra connections allowed during traffic spikes (20 for burst handling)
# - pool_pre_ping: Checks if connection is alive before using (prevents stale connections)
# - pool_recycle: Recycle connections after 5 min (Supavisor/Neon compatibility)
# Pool Configuration: Use NullPool for testing to avoid connection leaks across loops
pool_args: Dict[str, Any] = {}
if "sqlite" in settings.DATABASE_URL:
    pool_args["poolclass"] = StaticPool
    connect_args["check_same_thread"] = False
elif settings.TESTING:
    pool_args["poolclass"] = NullPool
else:
    pool_args["pool_size"] = settings.DB_POOL_SIZE
    pool_args["max_overflow"] = settings.DB_MAX_OVERFLOW

# Determine the actual URL to use. If testing, default to in-memory sqlite to avoid side-effects.
effective_url = settings.DATABASE_URL
if settings.TESTING and "sqlite" not in effective_url:
    effective_url = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    effective_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=300,   # Recycle every 5 min for Supavisor
    connect_args=connect_args,
    **pool_args
)

SLOW_QUERY_THRESHOLD_SECONDS = 0.2

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, _cursor, _statement, _parameters, _context, _executemany):
    """Record query start time."""
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())

@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, _cursor, statement, parameters, _context, _executemany):
    """Log slow queries."""
    total = time.perf_counter() - conn.info["query_start_time"].pop(-1)
    if total > SLOW_QUERY_THRESHOLD_SECONDS:
        logger.warning(
            "slow_query_detected",
            duration_seconds=round(total, 3),
            statement=statement[:200] + "..." if len(statement) > 200 else statement,
            parameters=str(parameters)[:100] if parameters else None
        )

# Session Factory: Creates new database sessions
# - expire_on_commit=False: Prevents lazy loading issues in async code
#   (objects remain accessible after commit without re-querying)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db(request: Request = None) -> AsyncSession:
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
                    if "postgresql" in str(session.bind.url if session.bind else ""):
                        await session.execute(
                            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                            {"tid": str(tenant_id)}
                        )
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
    if "postgresql" in str(session.bind.url if session.bind else ""):
        try:
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)}
            )
        except Exception as e:
            logger.warning("failed_to_set_rls_config_in_session", error=str(e))

@event.listens_for(Engine, "before_cursor_execute", retval=True)
def check_rls_policy(conn, _cursor, statement, parameters, _context, _executemany):
    """
    PRODUCTION: Hardened Multi-Tenancy RLS Enforcement
    
    This listener ENFORCES Row-Level Security by raising an exception if a query runs 
    without proper tenant context. This prevents accidental data leaks across tenants.
    """
    # Skip enforcement in tests to avoid dialect-specific transaction issues (e.g. prepare)
    if settings.TESTING:
        return statement, parameters
        
    # Skip internal/system queries or migrations
    from app.shared.core.constants import RLS_EXEMPT_TABLES
    stmt_lower = statement.lower()
    
    if "select 1" in stmt_lower or "select version()" in stmt_lower or "select pg_is_in_recovery()" in stmt_lower:
        return statement, parameters

    for table in RLS_EXEMPT_TABLES:
        if f"from {table}" in stmt_lower or f"into {table}" in stmt_lower or f"update {table}" in stmt_lower:
            return statement, parameters


    # Identify the state from the connection info
    rls_status = conn.info.get("rls_context_set")

    # PRODUCTION: Raise exception on RLS context missing (False)
    # Note: None is allowed for system/internal connections that don't go through get_db
    # but for all request-bound sessions, it will be True or False.
    if rls_status is False:
        try:
            if statement.split():
                RLS_CONTEXT_MISSING.labels(statement_type=statement.split()[0].upper()).inc()
        except Exception as e:
            logger.debug("rls_metric_increment_failed", error=str(e))
        
        logger.critical(
            "rls_enforcement_violation_detected",
            statement=statement[:200],
            error="Query executed WITHOUT tenant insulation set. RLS policy violated!"
        )
        
        # PRODUCTION: Hard exception - no execution allowed
        raise ValdrixException(
            message="RLS context missing - query execution aborted",
            code="rls_enforcement_failed",
            status_code=500,
            details={
                "reason": "Multi-tenant isolation enforcement failed",
                "action": "This is a critical security error. Check that all DB sessions are initialized with tenant context."
            }
        )
    
    return statement, parameters

