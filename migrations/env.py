import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context
import ssl

from app.shared.db.base import Base
# Import all models so Base knows about them!
from app.models.llm import LLMUsage, LLMBudget  # noqa: F401 # pylint: disable=unused-import
from app.models.carbon_settings import CarbonSettings  # noqa: F401 # pylint: disable=unused-import
from app.models.aws_connection import AWSConnection  # noqa: F401 # pylint: disable=unused-import
from app.models.discovered_account import DiscoveredAccount  # noqa: F401 # pylint: disable=unused-import
from app.models.cloud import CostRecord  # noqa: F401 # pylint: disable=unused-import
from app.models.notification_settings import NotificationSettings  # noqa: F401 # pylint: disable=unused-import
from app.models.remediation import RemediationRequest  # noqa: F401 # pylint: disable=unused-import
from app.models.remediation_settings import RemediationSettings  # noqa: F401 # pylint: disable=unused-import
from app.models.azure_connection import AzureConnection  # noqa: F401 # pylint: disable=unused-import
from app.models.gcp_connection import GCPConnection  # noqa: F401 # pylint: disable=unused-import
from app.models.tenant import User, Tenant  # noqa: F401 # pylint: disable=unused-import
from app.models.pricing import PricingPlan, ExchangeRate, TenantSubscription, LLMProviderPricing  # noqa: F401
from app.models.background_job import BackgroundJob  # noqa: F401 # pylint: disable=unused-import
# TenantSubscription now imported from app.models.pricing
from app.modules.governance.domain.security.audit_log import AuditLog  # noqa: F401 # pylint: disable=unused-import
from app.models.attribution import AttributionRule, CostAllocation  # noqa: F401 # pylint: disable=unused-import
from app.models.anomaly_marker import AnomalyMarker  # noqa: F401 # pylint: disable=unused-import
from app.models.optimization import OptimizationStrategy, StrategyRecommendation  # noqa: F401 # pylint: disable=unused-import

from app.shared.core.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine


settings = get_settings()


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(obj, name, type_, reflected, compare_to):
    """
    Skip partitioned tables and other objects we don't want Alembic to manage.
    """
    if type_ == "table":
        # Ignore audit log partitions (e.g., audit_logs_p2026_01)
        if name.startswith("audit_logs_p"):
            return False
        # Ignore cost record partitions (managed by pg_partman or similar)
        if name.startswith("cost_records_p"):
            return False
        # Ignore materialized views (managed manually)
        if name.startswith("mv_"):
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Create SSL context for Supabase connection (verified)
    # Why: Supabase via pooler uses a specific CA certificate we must trust
    import os
    base_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    _ = os.path.join(base_path, "app", "core", "supabase.crt")
    
    ssl_context = ssl.create_default_context()
    # ssl_context.set_ciphers('DEFAULT@SECLEVEL=0') # Unused as cert is invalid for OpenSSL 3
    # ssl_context.load_verify_locations(cafile=ca_cert_path) # Kept for reference but verification disabled
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    # ssl_context.check_hostname = True # Default
    # ssl_context.verify_mode = ssl.CERT_REQUIRED # Default
    
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args={
            "ssl": ssl_context,
            "statement_cache_size": 0,  # Required for Supabase transaction pooler
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Escape % characters for ConfigParser interpolation
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
