"""repair drift for background_jobs and strategy_recommendations

Revision ID: 3741a713f494
Revises: b35982d24a2e
Create Date: 2026-02-15 09:33:30.255697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '3741a713f494'
down_revision: Union[str, Sequence[str], None] = 'b35982d24a2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("background_jobs"):
        cols = {c["name"]: c for c in insp.get_columns("background_jobs")}

        if "updated_at" not in cols:
            # Add with a default, backfill, then enforce NOT NULL for API stability.
            op.add_column(
                "background_jobs",
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("now()"),
                ),
            )

        # Backfill nulls (covers both new column and any drifted nullable column).
        op.execute(
            sa.text(
                "UPDATE background_jobs "
                "SET updated_at = COALESCE(updated_at, created_at, now()) "
                "WHERE updated_at IS NULL"
            )
        )

        # Ensure the column is NOT NULL and has a server default.
        op.alter_column(
            "background_jobs",
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )

        expected_idx = "ix_background_jobs_updated_at"
        existing_indexes = {i["name"] for i in insp.get_indexes("background_jobs")}
        if expected_idx not in existing_indexes:
            op.create_index(
                expected_idx, "background_jobs", ["updated_at"], unique=False
            )

    if insp.has_table("strategy_recommendations"):
        cols = {c["name"] for c in insp.get_columns("strategy_recommendations")}

        if "estimated_monthly_savings_low" not in cols:
            op.add_column(
                "strategy_recommendations",
                sa.Column(
                    "estimated_monthly_savings_low",
                    sa.Numeric(precision=12, scale=2),
                    nullable=True,
                ),
            )

        if "estimated_monthly_savings_high" not in cols:
            op.add_column(
                "strategy_recommendations",
                sa.Column(
                    "estimated_monthly_savings_high",
                    sa.Numeric(precision=12, scale=2),
                    nullable=True,
                ),
            )

        if "break_even_months" not in cols:
            op.add_column(
                "strategy_recommendations",
                sa.Column(
                    "break_even_months",
                    sa.Numeric(precision=8, scale=2),
                    nullable=True,
                ),
            )

        if "confidence_score" not in cols:
            op.add_column(
                "strategy_recommendations",
                sa.Column(
                    "confidence_score",
                    sa.Numeric(precision=4, scale=3),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("strategy_recommendations"):
        cols = {c["name"] for c in insp.get_columns("strategy_recommendations")}
        for name in [
            "confidence_score",
            "break_even_months",
            "estimated_monthly_savings_high",
            "estimated_monthly_savings_low",
        ]:
            if name in cols:
                op.drop_column("strategy_recommendations", name)

    if insp.has_table("background_jobs"):
        cols = {c["name"] for c in insp.get_columns("background_jobs")}
        if "updated_at" in cols:
            existing_indexes = {i["name"] for i in insp.get_indexes("background_jobs")}
            idx = "ix_background_jobs_updated_at"
            if idx in existing_indexes:
                op.drop_index(idx, table_name="background_jobs")
            op.drop_column("background_jobs", "updated_at")
