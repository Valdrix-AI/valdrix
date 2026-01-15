import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

# Validation: Fail fast if database URL is not configured
# Why: Better to crash on startup than fail silently on first request
if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is not set. Check your .env file.")

# SSL Context: Configurable SSL modes for different environments
# Options: disable, require, verify-ca, verify-full
ssl_mode = settings.DB_SSL_MODE.lower()
connect_args = {"statement_cache_size": 0}  # Required for Supavisor

if ssl_mode == "disable":
    # WARNING: Only for local development with no SSL
    logger.warning("database_ssl_disabled",
                   msg="SSL disabled - INSECURE, do not use in production!")
    connect_args["ssl"] = False

elif ssl_mode == "require":
    # Encryption enforced, but no certificate verification
    # Suitable for Supabase pooler where we trust the endpoint but don't have a CA cert
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_context
    logger.info("database_ssl_require", msg="SSL enabled (encrypted, no cert verification)")

elif ssl_mode in ("verify-ca", "verify-full"):
    # Full verification - recommended for production with known CA
    if not settings.DB_SSL_CA_CERT_PATH:
        raise ValueError(f"DB_SSL_CA_CERT_PATH required for ssl_mode={ssl_mode}")
    ssl_context = ssl.create_default_context(cafile=settings.DB_SSL_CA_CERT_PATH)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = (ssl_mode == "verify-full")
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
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,        # Zero-Budget: Reduced to stay within free tier limits
    max_overflow=10,    # Zero-Budget: Reduced to prevent connection exhaustion
    pool_pre_ping=True,
    pool_recycle=300,   # Recycle every 5 min for Supavisor
    connect_args=connect_args,
)

# Session Factory: Creates new database sessions
# - expire_on_commit=False: Prevents lazy loading issues in async code
#   (objects remain accessible after commit without re-querying)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


from fastapi import Request
from sqlalchemy import text

async def get_db(request: Request = None) -> AsyncSession:
    """
    FastAPI dependency that provides a database session with RLS context.
    """
    async with async_session_maker() as session:
        # If we have a tenant_id in request state, set it in the DB session for RLS
        # current_setting('app.current_tenant_id', TRUE) in SQL will return this value
        if request and hasattr(request.state, "tenant_id"):
            tenant_id = request.state.tenant_id
            if tenant_id:
                try:
                    await session.execute(
                        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                        {"tid": str(tenant_id)}
                    )
                except Exception as e:
                    logger.warning("rls_context_set_failed", error=str(e))

        try:
            yield session
        finally:
            await session.close()
