"""add_canonical_charge_columns_to_cost_records

Revision ID: 2a7b1d9c4e01
Revises: 1db8130b8ee6
Create Date: 2026-02-12 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2a7b1d9c4e01"
down_revision: Union[str, Sequence[str], None] = "1db8130b8ee6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cost_records",
        sa.Column(
            "canonical_charge_category",
            sa.String(),
            nullable=False,
            server_default=sa.text("'unmapped'"),
        ),
    )
    op.add_column(
        "cost_records",
        sa.Column("canonical_charge_subcategory", sa.String(), nullable=True),
    )
    op.add_column(
        "cost_records",
        sa.Column(
            "canonical_mapping_version",
            sa.String(),
            nullable=False,
            server_default=sa.text("'focus-1.3-v1'"),
        ),
    )
    op.create_index(
        op.f("ix_cost_records_canonical_charge_category"),
        "cost_records",
        ["canonical_charge_category"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_cost_records_canonical_charge_category"),
        table_name="cost_records",
    )
    op.drop_column("cost_records", "canonical_mapping_version")
    op.drop_column("cost_records", "canonical_charge_subcategory")
    op.drop_column("cost_records", "canonical_charge_category")
