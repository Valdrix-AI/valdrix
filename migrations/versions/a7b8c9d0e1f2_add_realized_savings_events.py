"""add_realized_savings_events

Revision ID: a7b8c9d0e1f2
Revises: f4a1b2c3d4e5
Create Date: 2026-02-14 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f4a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "realized_savings_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("remediation_request_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("service", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("baseline_start_date", sa.Date(), nullable=False),
        sa.Column("baseline_end_date", sa.Date(), nullable=False),
        sa.Column("measurement_start_date", sa.Date(), nullable=False),
        sa.Column("measurement_end_date", sa.Date(), nullable=False),
        sa.Column("baseline_total_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("baseline_observed_days", sa.Integer(), nullable=False),
        sa.Column("measurement_total_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("measurement_observed_days", sa.Integer(), nullable=False),
        sa.Column("baseline_avg_daily_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("measurement_avg_daily_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("realized_avg_daily_savings_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("realized_monthly_savings_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("monthly_multiplier_days", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remediation_request_id"], ["remediation_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "remediation_request_id",
            name="uix_realized_savings_tenant_remediation",
        ),
    )

    op.create_index(op.f("ix_realized_savings_events_tenant_id"), "realized_savings_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_realized_savings_events_remediation_request_id"), "realized_savings_events", ["remediation_request_id"], unique=False)
    op.create_index(op.f("ix_realized_savings_events_provider"), "realized_savings_events", ["provider"], unique=False)
    op.create_index(op.f("ix_realized_savings_events_account_id"), "realized_savings_events", ["account_id"], unique=False)
    op.create_index(op.f("ix_realized_savings_events_resource_id"), "realized_savings_events", ["resource_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_realized_savings_events_resource_id"), table_name="realized_savings_events")
    op.drop_index(op.f("ix_realized_savings_events_account_id"), table_name="realized_savings_events")
    op.drop_index(op.f("ix_realized_savings_events_provider"), table_name="realized_savings_events")
    op.drop_index(op.f("ix_realized_savings_events_remediation_request_id"), table_name="realized_savings_events")
    op.drop_index(op.f("ix_realized_savings_events_tenant_id"), table_name="realized_savings_events")
    op.drop_table("realized_savings_events")

