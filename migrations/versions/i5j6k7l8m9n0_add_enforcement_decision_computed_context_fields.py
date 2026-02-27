"""add enforcement decision computed context fields

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-02-25 01:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i5j6k7l8m9n0"
down_revision: Union[str, Sequence[str], None] = "h4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enforcement_decisions",
        sa.Column("burn_rate_daily_usd", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "enforcement_decisions",
        sa.Column("forecast_eom_usd", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "enforcement_decisions",
        sa.Column("risk_class", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "enforcement_decisions",
        sa.Column("risk_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "enforcement_decisions",
        sa.Column("anomaly_signal", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_enforcement_decisions_risk_class",
        "enforcement_decisions",
        ["risk_class"],
        unique=False,
    )

    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("burn_rate_daily_usd", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("forecast_eom_usd", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("risk_class", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("risk_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("anomaly_signal", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enforcement_decision_ledger", "anomaly_signal")
    op.drop_column("enforcement_decision_ledger", "risk_score")
    op.drop_column("enforcement_decision_ledger", "risk_class")
    op.drop_column("enforcement_decision_ledger", "forecast_eom_usd")
    op.drop_column("enforcement_decision_ledger", "burn_rate_daily_usd")

    op.drop_index(
        "ix_enforcement_decisions_risk_class",
        table_name="enforcement_decisions",
    )
    op.drop_column("enforcement_decisions", "anomaly_signal")
    op.drop_column("enforcement_decisions", "risk_score")
    op.drop_column("enforcement_decisions", "risk_class")
    op.drop_column("enforcement_decisions", "forecast_eom_usd")
    op.drop_column("enforcement_decisions", "burn_rate_daily_usd")
