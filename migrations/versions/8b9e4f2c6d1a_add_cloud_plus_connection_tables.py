"""add_cloud_plus_connection_tables

Revision ID: 8b9e4f2c6d1a
Revises: 5f3a9c2d1e8b
Create Date: 2026-02-12 09:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b9e4f2c6d1a"
down_revision: Union[str, Sequence[str], None] = "5f3a9c2d1e8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "saas_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vendor", sa.String(length=100), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("api_key", sa.String(length=1024), nullable=True),
        sa.Column("spend_feed", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vendor", "name", name="uq_tenant_saas_vendor_name"),
    )
    op.create_index(op.f("ix_saas_connections_tenant_id"), "saas_connections", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_saas_connections_vendor"), "saas_connections", ["vendor"], unique=False)

    op.create_table(
        "license_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vendor", sa.String(length=100), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("api_key", sa.String(length=1024), nullable=True),
        sa.Column("license_feed", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vendor", "name", name="uq_tenant_license_vendor_name"),
    )
    op.create_index(op.f("ix_license_connections_tenant_id"), "license_connections", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_license_connections_vendor"), "license_connections", ["vendor"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_license_connections_vendor"), table_name="license_connections")
    op.drop_index(op.f("ix_license_connections_tenant_id"), table_name="license_connections")
    op.drop_table("license_connections")

    op.drop_index(op.f("ix_saas_connections_vendor"), table_name="saas_connections")
    op.drop_index(op.f("ix_saas_connections_tenant_id"), table_name="saas_connections")
    op.drop_table("saas_connections")
