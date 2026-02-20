import asyncio
from logging.config import fileConfig
from typing import Any
import re

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
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
from app.models.saas_connection import SaaSConnection  # noqa: F401 # pylint: disable=unused-import
from app.models.license_connection import LicenseConnection  # noqa: F401 # pylint: disable=unused-import
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


_COST_RECORD_PARTITION_RE = re.compile(r"^cost_records_\d{4}_\d{2}$")


def _is_ignored_partition_table(name: str) -> bool:
    if name.startswith("audit_logs_p"):
        return True
    if _COST_RECORD_PARTITION_RE.match(name):
        return True
    return False


def include_object(obj, name, type_, reflected, compare_to):
    """
    Skip partitioned tables and other objects we don't want Alembic to manage.
    """
    obj_name = name or ""

    if type_ == "table":
        # Ignore partition child tables managed outside Alembic.
        if _is_ignored_partition_table(obj_name):
            return False
        # Ignore materialized views (managed manually)
        if obj_name.startswith("mv_"):
            return False

    # Some backends surface partition indexes/constraints independently.
    # Skip objects attached to ignored partition tables.
    if type_ in {"index", "foreign_key_constraint", "unique_constraint"}:
        table_name = getattr(getattr(obj, "table", None), "name", None)
        if isinstance(table_name, str) and _is_ignored_partition_table(table_name):
            return False

    return True


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """
    Suppress type diffs that are semantically equivalent in this codebase.
    """
    inspected_name = type(inspected_type).__name__
    metadata_name = type(metadata_type).__name__

    # JSON/JSONB variants are handled with SQLAlchemy variants; autogen can report
    # noisy JSON vs JSON(astext_type=Text()) changes for PostgreSQL.
    if inspected_name in {"JSON", "JSONB"} and metadata_name in {"JSON", "JSONB"}:
        return False
    if isinstance(inspected_type, postgresql.JSON) and isinstance(metadata_type, sa.JSON):
        return False

    # SQLAlchemy-Utils encrypted type stores as text-ish DB types.
    if metadata_name == "StringEncryptedType":
        return False

    return None


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
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    ssl_mode = (settings.DB_SSL_MODE or "require").lower()
    connect_args: dict[str, Any] = {"statement_cache_size": 0}

    if ssl_mode == "disable":
        connect_args["ssl"] = False
    elif ssl_mode == "require":
        # Supabase/Supavisor pooler often works best with "require" semantics:
        # encrypted transport without enforcing certificate-chain validation.
        connect_args["ssl"] = "require"
    elif ssl_mode in {"verify-ca", "verify-full"}:
        if not settings.DB_SSL_CA_CERT_PATH:
            raise ValueError(f"DB_SSL_CA_CERT_PATH is required when DB_SSL_MODE={ssl_mode}")
        ssl_context = ssl.create_default_context(cafile=settings.DB_SSL_CA_CERT_PATH)
        ssl_context.check_hostname = ssl_mode == "verify-full"
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        connect_args["ssl"] = ssl_context
    else:
        raise ValueError(
            f"Invalid DB_SSL_MODE: {ssl_mode}. Use: disable, require, verify-ca, verify-full"
        )

    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args=connect_args,
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
