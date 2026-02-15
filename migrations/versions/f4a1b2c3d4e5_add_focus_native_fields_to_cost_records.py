"""add_focus_native_fields_to_cost_records

Revision ID: f4a1b2c3d4e5
Revises: c3d4e5f6a7b8
Create Date: 2026-02-14 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f4a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cost_records",
        sa.Column(
            "resource_id",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column("cost_records", sa.Column("usage_amount", sa.Numeric(18, 8), nullable=True))
    op.add_column("cost_records", sa.Column("usage_unit", sa.String(length=64), nullable=True))
    op.add_column(
        "cost_records",
        sa.Column(
            "tags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )

    # Expand uniqueness to include resource_id while preserving idempotency
    # for sources that do not provide it (resource_id defaults to '').
    op.execute("ALTER TABLE cost_records DROP CONSTRAINT IF EXISTS uix_account_cost_granularity")
    op.create_unique_constraint(
        "uix_account_cost_granularity",
        "cost_records",
        ["account_id", "timestamp", "service", "region", "usage_type", "recorded_at", "resource_id"],
    )

    op.create_index(op.f("ix_cost_records_resource_id"), "cost_records", ["resource_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cost_records_resource_id"), table_name="cost_records")

    op.execute("ALTER TABLE cost_records DROP CONSTRAINT IF EXISTS uix_account_cost_granularity")
    op.create_unique_constraint(
        "uix_account_cost_granularity",
        "cost_records",
        ["account_id", "timestamp", "service", "region", "usage_type", "recorded_at"],
    )

    op.drop_column("cost_records", "tags")
    op.drop_column("cost_records", "usage_unit")
    op.drop_column("cost_records", "usage_amount")
    op.drop_column("cost_records", "resource_id")

