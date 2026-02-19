"""add charge audit fields to tenant_subscriptions

Revision ID: e6f7a8b9c0d1
Revises: d033af62b03e
Create Date: 2026-02-19 02:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d033af62b03e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tenant_subscriptions",
        sa.Column("billing_currency", sa.String(length=3), nullable=False, server_default="NGN"),
    )
    op.add_column(
        "tenant_subscriptions",
        sa.Column("last_charge_amount_subunits", sa.Numeric(precision=20, scale=0), nullable=True),
    )
    op.add_column(
        "tenant_subscriptions",
        sa.Column("last_charge_fx_rate", sa.Numeric(precision=12, scale=6), nullable=True),
    )
    op.add_column(
        "tenant_subscriptions",
        sa.Column("last_charge_fx_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tenant_subscriptions",
        sa.Column("last_charge_reference", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tenant_subscriptions",
        sa.Column("last_charge_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tenant_subscriptions", "last_charge_at")
    op.drop_column("tenant_subscriptions", "last_charge_reference")
    op.drop_column("tenant_subscriptions", "last_charge_fx_provider")
    op.drop_column("tenant_subscriptions", "last_charge_fx_rate")
    op.drop_column("tenant_subscriptions", "last_charge_amount_subunits")
    op.drop_column("tenant_subscriptions", "billing_currency")
