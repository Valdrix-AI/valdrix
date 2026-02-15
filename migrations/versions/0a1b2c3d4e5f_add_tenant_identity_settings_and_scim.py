"""Add tenant identity settings and SCIM deprovisioning support.

Revision ID: 0a1b2c3d4e5f
Revises: f1a2b3c4d5e6
Create Date: 2026-02-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_identity_settings",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("sso_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "allowed_email_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("scim_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scim_bearer_token", sa.String(length=1024), nullable=True),
        sa.Column("scim_token_bidx", sa.String(length=64), nullable=True),
        sa.Column("scim_last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_tenant_identity_settings_tenant_id_tenants"),
        ),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_identity_settings_tenant_id"),
    )
    op.create_index(
        op.f("ix_tenant_identity_settings_tenant_id"),
        "tenant_identity_settings",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_identity_settings_scim_token_bidx"),
        "tenant_identity_settings",
        ["scim_token_bidx"],
        unique=False,
    )

    # RLS: keep consistent with other tenant-scoped settings tables.
    op.execute("ALTER TABLE tenant_identity_settings ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_identity_settings_isolation_policy ON tenant_identity_settings
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
        """
    )

    # SCIM deprovisioning support.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true"
        )
    else:
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)

    # Clean up server defaults set for safe backfill.
    op.alter_column("tenant_identity_settings", "allowed_email_domains", server_default=None)
    op.alter_column("tenant_identity_settings", "sso_enabled", server_default=None)
    op.alter_column("tenant_identity_settings", "scim_enabled", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_column("users", "is_active")

    op.execute(
        "DROP POLICY IF EXISTS tenant_identity_settings_isolation_policy ON tenant_identity_settings"
    )
    op.execute("ALTER TABLE tenant_identity_settings DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_tenant_identity_settings_scim_token_bidx"), table_name="tenant_identity_settings")
    op.drop_index(op.f("ix_tenant_identity_settings_tenant_id"), table_name="tenant_identity_settings")
    op.drop_table("tenant_identity_settings")

