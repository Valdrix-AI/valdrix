"""add_unit_economics_settings_table

Revision ID: 4d2f9a1b7c3e
Revises: 7c9e1a8d4b2f
Create Date: 2026-02-12 05:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d2f9a1b7c3e"
down_revision: Union[str, Sequence[str], None] = "7c9e1a8d4b2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "unit_economics_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("default_request_volume", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("default_workload_volume", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("default_customer_volume", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("anomaly_threshold_percent", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("unit_economics_settings")
