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
    pool_size=10,       # Phase 7: Increased for 10K user scaling
    max_overflow=20,    # Phase 7: Handle traffic bursts
    pool_pre_ping=True,
    pool_recycle=300,   # Phase 7: Recycle every 5 min for Supavisor
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


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a database session.

    Usage in endpoint:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()

    What it does:
    1. Creates a new session from the pool
    2. Yields it to the endpoint
    3. Closes/returns it to pool after request completes

    Why generator (yield):
        Ensures cleanup happens even if endpoint throws an exception
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
