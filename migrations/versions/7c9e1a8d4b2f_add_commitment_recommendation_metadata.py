"""add_commitment_recommendation_metadata

Revision ID: 7c9e1a8d4b2f
Revises: 2a7b1d9c4e01
Create Date: 2026-02-12 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c9e1a8d4b2f"
down_revision: Union[str, Sequence[str], None] = "2a7b1d9c4e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "strategy_recommendations",
        sa.Column("estimated_monthly_savings_low", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "strategy_recommendations",
        sa.Column("estimated_monthly_savings_high", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "strategy_recommendations",
        sa.Column("break_even_months", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        "strategy_recommendations",
        sa.Column("confidence_score", sa.Numeric(precision=4, scale=3), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("strategy_recommendations", "confidence_score")
    op.drop_column("strategy_recommendations", "break_even_months")
    op.drop_column("strategy_recommendations", "estimated_monthly_savings_high")
    op.drop_column("strategy_recommendations", "estimated_monthly_savings_low")
