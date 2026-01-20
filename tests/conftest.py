import os
# Item 1: Disable DB SSL and Rate Limiting for all tests BEFORE any app imports
os.environ["DB_SSL_MODE"] = "disable"
os.environ["RATELIMIT_ENABLED"] = "False"

import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from app.main import app

# Ensure all models are registered in the metadata for SQLAlchemy mappers (Item 3)
from app.models.tenant import Tenant, User
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.remediation import RemediationRequest
from app.models.security import OIDCKey
from app.services.security.audit_log import AuditLog
from app.models.llm import LLMUsage, LLMBudget
from app.models.background_job import BackgroundJob
from app.models.discovered_account import DiscoveredAccount
from app.models.pricing import PricingPlan, ExchangeRate
from app.models.notification_settings import NotificationSettings
from app.models.carbon_settings import CarbonSettings
from app.models.remediation_settings import RemediationSettings
from app.models.attribution import AttributionRule, CostAllocation
from app.models.cloud import CostRecord, CloudAccount

@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """Manually disable rate limiting for every test."""
    from app.core.rate_limit import get_limiter
    limiter = get_limiter()
    limiter.enabled = False
    yield
    limiter.enabled = True
from app.db.session import async_session_maker
from sqlalchemy.ext.asyncio import AsyncSession

_TABLES_CREATED = False

async def _create_tables():
    """Helper to create all tables in the test database."""
    from app.db.base import Base

    from app.db.session import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Create default partition for cost_records (required for partitioned table)
        await conn.execute(text("CREATE TABLE IF NOT EXISTS cost_records_default PARTITION OF cost_records DEFAULT"))
        # Create default partition for audit_logs
        await conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs_default PARTITION OF audit_logs DEFAULT"))

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
def mock_settings():
    """Globally override settings for all tests."""
    from app.core.config import get_settings, Settings
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()
    test_db_url = "postgresql+asyncpg://agentkern:agentkern_secret@localhost:5432/agentkern_identity"
    start_settings = Settings(
        DATABASE_URL=test_db_url,
        TESTING=True,
        SUPABASE_JWT_SECRET="test-secret",
        ENCRYPTION_KEY=test_key,
        DB_POOL_SIZE=5,
        DB_MAX_OVERFLOW=0,
        DB_SSL_MODE="disable",
        RATELIMIT_ENABLED=False
    )
    
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: start_settings
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.core.security.settings", start_settings)
        mp.setattr("app.db.session.settings", start_settings)
        mp.setattr("app.main.settings", start_settings)
        
        # Patch the engine and session maker in session.py
        from app.db import session
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        
        # Use NullPool for tests to avoid connection leaks across loops
        session.engine = create_async_engine(
            test_db_url,
            poolclass=NullPool,
            connect_args={"statement_cache_size": 0}
        )
        session.async_session_maker.configure(bind=session.engine)
        
        # Initialize schema synchronously for the session
        asyncio.run(_create_tables())
        
        yield start_settings
    
    app.dependency_overrides.clear()

@pytest.fixture
async def db(mock_settings) -> AsyncGenerator[AsyncSession, None]:
    """Provides a clean database session for each test, ensuring fresh engine."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    
    # Recreate engine to avoid loop-attachment errors from session-level setup
    test_engine = create_async_engine(
        mock_settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0}
    )
    
    async with test_engine.connect() as connection:
        trans = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    
    await test_engine.dispose()

@pytest.fixture
async def ac() -> AsyncGenerator[AsyncClient, None]:
    """Async client fixture for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
