"""Add SCIM Groups and membership tracking.

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-02-14

Adds DB-backed SCIM groups to support IdPs that push group objects and manage
membership via /Groups endpoints (instead of embedding groups in /Users payloads).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scim_groups",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("display_name_norm", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_id_norm", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_scim_groups_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scim_groups")),
        sa.UniqueConstraint(
            "tenant_id",
            "display_name_norm",
            name="uq_scim_group_tenant_display_name_norm",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "external_id_norm",
            name="uq_scim_group_tenant_external_id_norm",
        ),
    )
    op.create_index(op.f("ix_scim_groups_tenant_id"), "scim_groups", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_scim_groups_display_name_norm"), "scim_groups", ["display_name_norm"], unique=False)
    op.create_index(op.f("ix_scim_groups_external_id_norm"), "scim_groups", ["external_id_norm"], unique=False)

    op.create_table(
        "scim_group_members",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_scim_group_members_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["scim_groups.id"],
            name=op.f("fk_scim_group_members_group_id_scim_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_scim_group_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scim_group_members")),
        sa.UniqueConstraint(
            "tenant_id",
            "group_id",
            "user_id",
            name="uq_scim_group_member_tenant_group_user",
        ),
    )
    op.create_index(op.f("ix_scim_group_members_tenant_id"), "scim_group_members", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_scim_group_members_group_id"), "scim_group_members", ["group_id"], unique=False)
    op.create_index(op.f("ix_scim_group_members_user_id"), "scim_group_members", ["user_id"], unique=False)

    # RLS (Postgres only). Safe to attempt in all envs (SQLite ignores / will error, so guard by dialect).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE scim_groups ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE scim_group_members ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY scim_groups_isolation_policy ON scim_groups
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
            """
        )
        op.execute(
            """
            CREATE POLICY scim_group_members_isolation_policy ON scim_group_members
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS scim_group_members_isolation_policy ON scim_group_members")
        op.execute("DROP POLICY IF EXISTS scim_groups_isolation_policy ON scim_groups")
        op.execute("ALTER TABLE scim_group_members DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE scim_groups DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_scim_group_members_user_id"), table_name="scim_group_members")
    op.drop_index(op.f("ix_scim_group_members_group_id"), table_name="scim_group_members")
    op.drop_index(op.f("ix_scim_group_members_tenant_id"), table_name="scim_group_members")
    op.drop_table("scim_group_members")

    op.drop_index(op.f("ix_scim_groups_external_id_norm"), table_name="scim_groups")
    op.drop_index(op.f("ix_scim_groups_display_name_norm"), table_name="scim_groups")
    op.drop_index(op.f("ix_scim_groups_tenant_id"), table_name="scim_groups")
    op.drop_table("scim_groups")

