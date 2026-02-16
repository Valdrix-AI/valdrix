"""add carbon factor sets

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-02-14

Adds audit-grade, DB-backed carbon factor sets so factor updates can be staged,
guardrailed, and activated without a code deploy.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carbon_factor_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'staged'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("factor_source", sa.String(length=255), nullable=False),
        sa.Column("factor_version", sa.String(length=64), nullable=False),
        sa.Column("factor_timestamp", sa.Date(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("factors_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_carbon_factor_sets_is_active"), "carbon_factor_sets", ["is_active"], unique=False)
    op.create_index(op.f("ix_carbon_factor_sets_status"), "carbon_factor_sets", ["status"], unique=False)
    op.create_index(op.f("ix_carbon_factor_sets_factor_version"), "carbon_factor_sets", ["factor_version"], unique=False)
    op.create_index(
        op.f("ix_carbon_factor_sets_factor_timestamp"),
        "carbon_factor_sets",
        ["factor_timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_carbon_factor_sets_factors_checksum_sha256"),
        "carbon_factor_sets",
        unique=False,
    )
    op.create_index(op.f("ix_carbon_factor_sets_created_by_user_id"), "carbon_factor_sets", ["created_by_user_id"], unique=False)

    op.create_table(
        "carbon_factor_update_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("old_factor_set_id", sa.Uuid(), nullable=True),
        sa.Column("new_factor_set_id", sa.Uuid(), nullable=True),
        sa.Column("old_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("new_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_carbon_factor_update_logs_recorded_at"),
        "carbon_factor_update_logs",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_carbon_factor_update_logs_action"),
        "carbon_factor_update_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_carbon_factor_update_logs_old_factor_set_id"),
        "carbon_factor_update_logs",
        ["old_factor_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_carbon_factor_update_logs_new_factor_set_id"),
        "carbon_factor_update_logs",
        ["new_factor_set_id"],
        unique=False,
    )
    op.create_index(op.f("ix_carbon_factor_update_logs_actor_user_id"), "carbon_factor_update_logs", ["actor_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_carbon_factor_update_logs_new_factor_set_id"), table_name="carbon_factor_update_logs")
    op.drop_index(op.f("ix_carbon_factor_update_logs_old_factor_set_id"), table_name="carbon_factor_update_logs")
    op.drop_index(op.f("ix_carbon_factor_update_logs_action"), table_name="carbon_factor_update_logs")
    op.drop_index(op.f("ix_carbon_factor_update_logs_recorded_at"), table_name="carbon_factor_update_logs")
    op.drop_table("carbon_factor_update_logs")

    op.drop_index(op.f("ix_carbon_factor_sets_factors_checksum_sha256"), table_name="carbon_factor_sets")
    op.drop_index(op.f("ix_carbon_factor_sets_factor_timestamp"), table_name="carbon_factor_sets")
    op.drop_index(op.f("ix_carbon_factor_sets_factor_version"), table_name="carbon_factor_sets")
    op.drop_index(op.f("ix_carbon_factor_sets_status"), table_name="carbon_factor_sets")
    op.drop_index(op.f("ix_carbon_factor_sets_is_active"), table_name="carbon_factor_sets")
    op.drop_table("carbon_factor_sets")

