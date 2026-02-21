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

# Set test environment BEFORE any app imports (Crucial for lru_cache behavior)
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-testing-at-least-32-bytes")
os.environ.setdefault("ENCRYPTION_KEY", "32-byte-long-test-encryption-key")
os.environ.setdefault("CSRF_SECRET_KEY", "test-csrf-secret-key-at-least-32-bytes")
os.environ.setdefault("KDF_SALT", "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=")
os.environ.setdefault("DB_SSL_MODE", "disable")
os.environ.setdefault("is_production", "false")

# Mock heavy dependencies only if they cause issues in specific environments
# sys.modules["codecarbon"] = MagicMock()
# sys.modules["pandas"] = MagicMock()
# sys.modules["pyarrow"] = MagicMock()
# sys.modules["pyarrow.parquet"] = MagicMock()
# sys.modules["pyarrow.lib"] = MagicMock()
# We don't mock numpy directly here to allow other libs that might need it a bit,
# but we mock the things that trigger the re-load of native extensions.

from uuid import uuid4
from decimal import Decimal
import pytest
import pytest_asyncio
import tenacity
from typing import AsyncGenerator, Generator, Optional
from datetime import datetime, timezone
from app.models.tenant import UserRole
from app.shared.core.pricing import PricingTier

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from fastapi.testclient import TestClient
    from httpx import AsyncClient

# Import test isolation utilities

# Environment variables are already set at the top

# Import all models to register them in SQLAlchemy mapper globally for all tests


def _register_models():
    # Import all models to register them in SQLAlchemy mapper globally for all tests
    # We do NOT catch ImportError anymore to expose broken models immediately
    from app.models.cloud import CloudAccount, CostRecord  # noqa: F401
    from app.models.aws_connection import AWSConnection  # noqa: F401
    from app.models.azure_connection import AzureConnection  # noqa: F401
    from app.models.gcp_connection import GCPConnection  # noqa: F401
    from app.models.saas_connection import SaaSConnection  # noqa: F401
    from app.models.license_connection import LicenseConnection  # noqa: F401
    from app.models.tenant import Tenant  # noqa: F401
    from app.models.remediation import RemediationRequest  # noqa: F401
    from app.models.security import OIDCKey  # noqa: F401
    from app.models.notification_settings import NotificationSettings  # noqa: F401
    from app.models.tenant_identity_settings import TenantIdentitySettings  # noqa: F401
    from app.models.sso_domain_mapping import SsoDomainMapping  # noqa: F401
    from app.models.scim_group import ScimGroup, ScimGroupMember  # noqa: F401
    from app.models.background_job import BackgroundJob  # noqa: F401
    from app.models.llm import LLMUsage, LLMBudget  # noqa: F401
    from app.models.attribution import AttributionRule  # noqa: F401
    from app.models.anomaly_marker import AnomalyMarker  # noqa: F401
    from app.models.carbon_settings import CarbonSettings  # noqa: F401
    from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog  # noqa: F401
    from app.models.discovered_account import DiscoveredAccount  # noqa: F401
    from app.models.discovery_candidate import DiscoveryCandidate  # noqa: F401
    from app.shared.core.pricing import PricingTier  # noqa: F401
    from app.models.remediation_settings import RemediationSettings  # noqa: F401
    from app.models.optimization import OptimizationStrategy, StrategyRecommendation  # noqa: F401
    from app.models.cost_audit import CostAuditLog  # noqa: F401
    from app.models.invoice import ProviderInvoice  # noqa: F401
    from app.models.realized_savings import RealizedSavingsEvent  # noqa: F401
    from app.models.unit_economics_settings import UnitEconomicsSettings  # noqa: F401
    from app.modules.governance.domain.security.audit_log import AuditLog  # noqa: F401


def pytest_configure(config):
    # Finding #5: Move model registration to pytest_configure
    # This prevents circular imports at module load time and 
    # ensures models are registered before any tests run.
    _register_models()


# Mock tiktoken if not installed
if "tiktoken" not in sys.modules:
    sys.modules["tiktoken"] = MagicMock()


# Mock tenacity to avoid retry delays
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
    """Create async SQLite engine for testing using a temporary file."""
    from sqlalchemy.ext.asyncio import create_async_engine
    import os

    db_file = f"test_{uuid4().hex}.sqlite"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()

    # Cleanup
    if os.path.exists(db_file):
        os.remove(db_file)


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator["AsyncSession", None]:
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
    from app.main import settings

    # Force TESTING mode to True to bypass CSRF and other secure middlewares
    settings.TESTING = True
    return valdrix_app


@pytest.fixture
def client(app) -> Generator["TestClient", None, None]:
    """Sync test client for FastAPI."""
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client(app, db, async_engine) -> AsyncGenerator["AsyncClient", None]:
    """Async test client for FastAPI. Overrides get_db to share test session."""
    from httpx import AsyncClient, ASGITransport
    from app.shared.db.session import get_db, get_system_db

    # Create test global session maker
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    test_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Patch all modules that use the global async_session_maker directly
    # to ensure they use our test session maker connected to the test DB.
    modules_to_patch = [
        "app.shared.db.session.async_session_maker",
        "app.shared.connections.oidc.async_session_maker",
        "app.modules.governance.api.v1.jobs.async_session_maker",
        "app.modules.governance.domain.jobs.cur_ingestion.async_session_maker",
        "app.modules.governance.domain.jobs.processor.async_session_maker",
        "app.tasks.scheduler_tasks.async_session_maker",
        "app.shared.llm.pricing_data.async_session_maker",
        "app.main.async_session_maker",
    ]

    from contextlib import ExitStack

    with ExitStack() as stack:
        for target in modules_to_patch:
            try:
                stack.enter_context(patch(target, test_session_maker))
            except (ImportError, AttributeError):
                # Some modules might not be loaded yet or don't have it
                continue

        # Store old override if any
        old_override = app.dependency_overrides.get(get_db)
        old_system_override = app.dependency_overrides.get(get_system_db)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_system_db] = lambda: db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            setattr(ac, "app", app)  # SEC: Attach app for dependency overrides in tests
            yield ac

        # Restore or remove override
        if old_override:
            app.dependency_overrides[get_db] = old_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_system_override:
            app.dependency_overrides[get_system_db] = old_system_override
        else:
            app.dependency_overrides.pop(get_system_db, None)


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
def mock_tenant_id():
    """Mock tenant ID for testing."""
    return uuid4()


@pytest.fixture
def mock_user_id():
    """Mock user ID for testing."""
    return uuid4()


@pytest.fixture
def mock_user(mock_tenant_id, mock_user_id):
    """Create mock CurrentUser for testing."""
    from app.shared.core.auth import CurrentUser

    return CurrentUser(
        id=mock_user_id,
        email="test@valdrix.io",
        tenant_id=mock_tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


@pytest.fixture
def member_user(mock_tenant_id, mock_user_id):
    """Create mock member user for testing."""
    from app.shared.core.auth import CurrentUser

    return CurrentUser(
        id=mock_user_id,
        email="member@valdrix.io",
        tenant_id=mock_tenant_id,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )


@pytest.fixture
async def test_tenant(db):
    """Create a test tenant for API tests."""
    from app.models.tenant import Tenant

    tenant = Tenant(id=uuid4(), name="API Test Tenant", plan="pro", is_deleted=False)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.fixture
async def test_remediation_request(db, test_tenant):
    """Create a test remediation request."""
    from app.models.remediation import (
        RemediationRequest,
        RemediationStatus,
        RemediationAction,
    )

    request = RemediationRequest(
        id=uuid4(),
        tenant_id=test_tenant.id,
        resource_id="i-test123",
        resource_type="ec2_instance",
        action=RemediationAction.STOP_INSTANCE,
        status=RemediationStatus.PENDING,
        requested_by_user_id=uuid4(),
        estimated_monthly_savings=Decimal("50.00"),
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


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
        usage_date: Optional[str] = None,
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


@pytest.fixture(autouse=True)
def clean_dependency_overrides(app):
    """Ensure dependency overrides are cleared after every test to prevent state bleeding."""
    # We yield first, so the test runs. Then we clear overrides.
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure settings are fresh for every test to prevent leakage."""
    from app.shared.core.config import get_settings
    from app.shared.db.session import reset_db_runtime
    import sys

    # 1. Clear the lru_cache
    get_settings.cache_clear()

    # 2. Reset the singleton if it was modified in-place
    # (Finding #L2: attribute-level mutation survives cache_clear if refs are held)
    settings = get_settings()
    settings.TESTING = True

    # 3. Reset DB runtime
    reset_db_runtime()

    yield

    # Teardown: ensure we don't leave it in a broken state
    get_settings.cache_clear()
    reset_db_runtime()
    
    # 4. Sync app.main if it exists
    if "app.main" in sys.modules:
        import app.main as app_main
        app_main.settings = get_settings()


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
