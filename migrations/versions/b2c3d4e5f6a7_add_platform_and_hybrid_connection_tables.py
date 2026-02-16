"""add_platform_and_hybrid_connection_tables

Revision ID: b2c3d4e5f6a7
Revises: 0a1b2c3d4e5f
Create Date: 2026-02-13

Adds Cloud+ domain expansion tables:
- platform_connections
- hybrid_connections

Also enables RLS + isolation policies for Cloud+ connection tables (saas/license/platform/hybrid)
to ensure tenant-scoped settings remain defense-in-depth protected.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_rls_with_policy(table: str, policy_name: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
    op.execute(
        f"""
        CREATE POLICY {policy_name} ON {table}
        USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
        """
    )


def upgrade() -> None:
    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vendor", sa.String(length=100), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("api_key", sa.String(length=1024), nullable=True),
        sa.Column("connector_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("spend_feed", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vendor", "name", name="uq_tenant_platform_vendor_name"),
    )
    op.create_index(op.f("ix_platform_connections_tenant_id"), "platform_connections", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_platform_connections_vendor"), "platform_connections", ["vendor"], unique=False)

    op.create_table(
        "hybrid_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vendor", sa.String(length=100), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("api_key", sa.String(length=1024), nullable=True),
        sa.Column("connector_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("spend_feed", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vendor", "name", name="uq_tenant_hybrid_vendor_name"),
    )
    op.create_index(op.f("ix_hybrid_connections_tenant_id"), "hybrid_connections", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_hybrid_connections_vendor"), "hybrid_connections", ["vendor"], unique=False)

    # RLS parity for Cloud+ connection tables.
    _enable_rls_with_policy("saas_connections", "saas_connections_isolation_policy")
    _enable_rls_with_policy("license_connections", "license_connections_isolation_policy")
    _enable_rls_with_policy("platform_connections", "platform_connections_isolation_policy")
    _enable_rls_with_policy("hybrid_connections", "hybrid_connections_isolation_policy")


def downgrade() -> None:
    # Drop policies (best-effort).
    op.execute("DROP POLICY IF EXISTS saas_connections_isolation_policy ON saas_connections")
    op.execute("DROP POLICY IF EXISTS license_connections_isolation_policy ON license_connections")
    op.execute("DROP POLICY IF EXISTS platform_connections_isolation_policy ON platform_connections")
    op.execute("DROP POLICY IF EXISTS hybrid_connections_isolation_policy ON hybrid_connections")

    op.drop_index(op.f("ix_hybrid_connections_vendor"), table_name="hybrid_connections")
    op.drop_index(op.f("ix_hybrid_connections_tenant_id"), table_name="hybrid_connections")
    op.drop_table("hybrid_connections")

    op.drop_index(op.f("ix_platform_connections_vendor"), table_name="platform_connections")
    op.drop_index(op.f("ix_platform_connections_tenant_id"), table_name="platform_connections")
    op.drop_table("platform_connections")

