"""add enforcement entitlement waterfall policy and credit pool fields

Revision ID: h4i5j6k7l8m9
Revises: g2h3i4j5k6l7
Create Date: 2026-02-25 00:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _credit_pool_enum() -> sa.Enum:
    return sa.Enum(
        "reserved",
        "emergency",
        name="enforcement_credit_pool_type",
        native_enum=False,
    )


def upgrade() -> None:
    op.add_column(
        "enforcement_policies",
        sa.Column("plan_monthly_ceiling_usd", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("enterprise_monthly_ceiling_usd", sa.Numeric(14, 4), nullable=True),
    )

    op.add_column(
        "enforcement_credit_grants",
        sa.Column(
            "pool_type",
            _credit_pool_enum(),
            nullable=False,
            server_default=sa.text("'reserved'"),
        ),
    )
    op.create_index(
        "ix_enforcement_credit_grants_pool_type",
        "enforcement_credit_grants",
        ["pool_type"],
        unique=False,
    )

    op.add_column(
        "enforcement_credit_reservation_allocations",
        sa.Column(
            "credit_pool_type",
            _credit_pool_enum(),
            nullable=False,
            server_default=sa.text("'reserved'"),
        ),
    )
    op.create_index(
        "ix_enforcement_credit_reservation_allocations_credit_pool_type",
        "enforcement_credit_reservation_allocations",
        ["credit_pool_type"],
        unique=False,
    )

    op.alter_column(
        "enforcement_credit_grants",
        "pool_type",
        server_default=None,
    )
    op.alter_column(
        "enforcement_credit_reservation_allocations",
        "credit_pool_type",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_enforcement_credit_reservation_allocations_credit_pool_type",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_column("enforcement_credit_reservation_allocations", "credit_pool_type")

    op.drop_index(
        "ix_enforcement_credit_grants_pool_type",
        table_name="enforcement_credit_grants",
    )
    op.drop_column("enforcement_credit_grants", "pool_type")

    op.drop_column("enforcement_policies", "enterprise_monthly_ceiling_usd")
    op.drop_column("enforcement_policies", "plan_monthly_ceiling_usd")
