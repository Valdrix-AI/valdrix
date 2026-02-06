"""
Global pytest fixtures for Valdrix test suite.

Provides:
- Async database session with SQLite in-memory
- Mock FastAPI test client
- Authentication fixtures
- Test data factories
- Test isolation utilities
"""
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from decimal import Decimal
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from datetime import datetime, timezone

# Import test isolation utilities
from .conftest_isolation import (
    TestIsolationManager, 
    MockStateManager, 
    AsyncEventLoopManager,
    DatabaseIsolationManager
)

# Set test environment BEFORE any app imports
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SUPABASE_JWT_SECRET"] = "test-jwt-secret-for-testing-at-least-32-bytes"
os.environ["ENCRYPTION_KEY"] = "32-byte-long-test-encryption-key"
os.environ["CSRF_SECRET_KEY"] = "test-csrf-secret-key-at-least-32-bytes"
os.environ["KDF_SALT"] = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=" # Base64 for 'KDF_SALT_FOR_TESTING_32_BYTES_OK'
os.environ["DB_SSL_MODE"] = "disable"  # Disable SSL for tests
os.environ["is_production"] = "false"  # Ensure we're not in production mode
 
# Import all models to register them in SQLAlchemy mapper globally for all tests
# Import all models to register them in SQLAlchemy mapper globally for all tests
def _register_models():
    try:
        from app.models.cloud import CloudAccount, CostRecord  # noqa: F401
        from app.models.aws_connection import AWSConnection  # noqa: F401
        from app.models.azure_connection import AzureConnection  # noqa: F401
        from app.models.gcp_connection import GCPConnection  # noqa: F401
        from app.models.tenant import Tenant  # noqa: F401
        from app.models.remediation import RemediationRequest  # noqa: F401
        from app.models.security import OIDCKey  # noqa: F401
        from app.models.notification_settings import NotificationSettings  # noqa: F401
        from app.models.background_job import BackgroundJob  # noqa: F401
        from app.models.llm import LLMUsage, LLMBudget  # noqa: F401
        from app.models.attribution import AttributionRule  # noqa: F401
        from app.models.anomaly_marker import AnomalyMarker  # noqa: F401
        from app.models.carbon_settings import CarbonSettings  # noqa: F401
        from app.models.discovered_account import DiscoveredAccount  # noqa: F401
        from app.models.pricing import PricingTier  # noqa: F401
        from app.models.remediation_settings import RemediationSettings  # noqa: F401
    except ImportError:
        pass


_register_models()








# Mock tiktoken if not installed
if "tiktoken" not in sys.modules:
    sys.modules["tiktoken"] = MagicMock()

# Mock tenacity to avoid retry delays
import tenacity
def mock_retry(*args, **kwargs):
    def decorator(f):
        return f
    return decorator
tenacity.retry = mock_retry


# ============================================================================
# Async Database Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def async_engine():
    """Create async SQLite in-memory engine for testing."""
    from sqlalchemy.ext.asyncio import create_async_engine
    
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator:
    """Create database tables and provide async session."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.shared.db.base import Base
    
    # Create all tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session factory
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Provide session with proper cleanup
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================

@pytest.fixture
def app():
    """Use the real Valdrix app for integration tests."""
    from app.main import app as valdrix_app
    return valdrix_app



@pytest.fixture
def client(app) -> Generator:
    """Sync test client for FastAPI."""
    from fastapi.testclient import TestClient
    
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client(app, db) -> AsyncGenerator:
    """Async test client for FastAPI. Overrides get_db to share test session."""
    from httpx import AsyncClient, ASGITransport
    from app.shared.db.session import get_db
    
    # Store old override if any
    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        
    # Restore or remove override
    if old_override:
        app.dependency_overrides[get_db] = old_override
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def ac(async_client):
    """Alias for async_client to match integration tests."""
    return async_client

@pytest_asyncio.fixture
async def db(db_session):
    """Alias for db_session to match integration tests."""
    return db_session



# ============================================================================
# Authentication Fixtures
# ============================================================================

@pytest.fixture
def mock_tenant_id() -> str:
    """Generate a mock tenant ID."""
    return str(uuid4())


@pytest.fixture
def mock_user_id() -> str:
    """Generate a mock user ID."""
    return str(uuid4())


@pytest.fixture
def mock_auth_context(mock_tenant_id, mock_user_id):
    """Create mock authentication context."""
    return {
        "tenant_id": mock_tenant_id,
        "user_id": mock_user_id,
        "role": "admin",
        "email": "test@valdrix.io",
    }


@pytest.fixture
def mock_jwt_token(mock_auth_context) -> str:
    """Create mock JWT token for testing."""
    import jwt
    
    payload = {
        **mock_auth_context,
        "exp": datetime.now(timezone.utc).timestamp() + 3600,
        "iat": datetime.now(timezone.utc).timestamp(),
    }
    return jwt.encode(payload, "test-jwt-secret-for-testing", algorithm="HS256")


# ============================================================================
# Mock Cloud Connection Fixtures
# ============================================================================

@pytest.fixture
def mock_aws_connection(mock_tenant_id):
    """Create mock AWS connection."""
    conn = MagicMock()
    conn.id = uuid4()
    conn.tenant_id = mock_tenant_id
    conn.provider = "aws"
    conn.role_arn = "arn:aws:iam::123456789012:role/ValdrixReadOnly"
    conn.external_id = "valdrix-test-external-id"
    conn.region = "us-east-1"
    conn.is_cur_enabled = True
    conn.cur_bucket = "valdrix-cur-test"
    conn.status = "active"
    return conn


@pytest.fixture
def mock_gcp_connection(mock_tenant_id):
    """Create mock GCP connection."""
    conn = MagicMock()
    conn.id = uuid4()
    conn.tenant_id = mock_tenant_id
    conn.provider = "gcp"
    conn.project_id = "valdrix-test-project"
    conn.billing_export_dataset = "billing_export"
    conn.status = "active"
    return conn


@pytest.fixture
def mock_azure_connection(mock_tenant_id):
    """Create mock Azure connection."""
    conn = MagicMock()
    conn.id = uuid4()
    conn.tenant_id = mock_tenant_id
    conn.provider = "azure"
    conn.subscription_id = "sub-12345678-test"
    conn.tenant_azure_id = "tenant-azure-test"
    conn.status = "active"
    return conn


# ============================================================================
# Test Data Factories
# ============================================================================

@pytest.fixture
def zombie_factory():
    """Factory for creating test zombie resources."""
    def _create_zombie(
        resource_type: str = "EC2",
        monthly_cost: float = 50.0,
        confidence: float = 0.85,
    ):
        return {
            "resource_id": f"arn:aws:ec2:us-east-1:123456789012:instance/i-{uuid4().hex[:8]}",
            "resource_type": resource_type,
            "resource_name": f"test-{resource_type.lower()}-{uuid4().hex[:4]}",
            "monthly_cost": Decimal(str(monthly_cost)),
            "confidence_score": confidence,
            "recommendation": f"Delete idle {resource_type}",
            "action": f"terminate_{resource_type.lower()}",
            "explainability_notes": f"Test {resource_type} has been idle for 7+ days",
        }
    return _create_zombie


@pytest.fixture
def cost_record_factory():
    """Factory for creating test cost records."""
    def _create_cost_record(
        service: str = "Amazon EC2",
        cost: float = 10.0,
        usage_date: str = None,
    ):
        return {
            "service": service,
            "cost": Decimal(str(cost)),
            "usage_date": usage_date or datetime.now(timezone.utc).date().isoformat(),
            "resource_id": f"i-{uuid4().hex[:8]}",
            "region": "us-east-1",
        }
    return _create_cost_record


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def set_testing_env():
    """Ensure TESTING is set for all tests."""
    os.environ["TESTING"] = "true"
    yield


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def mock_llm_response():
    """Mock LLM analysis response."""
    return {
        "summary": "Test analysis summary",
        "recommendations": ["Recommendation 1", "Recommendation 2"],
        "confidence": 0.9,
        "tokens_used": {"input": 500, "output": 200},
    }
