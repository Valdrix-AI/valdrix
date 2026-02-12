"""enforce_free_trial_tier_constraints

Revision ID: 5f3a9c2d1e8b
Revises: 4d2f9a1b7c3e
Create Date: 2026-02-12 06:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f3a9c2d1e8b"
down_revision: Union[str, Sequence[str], None] = "4d2f9a1b7c3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALLOWED_TIERS_SQL = "('free_trial', 'starter', 'growth', 'pro', 'enterprise')"


def upgrade() -> None:
    """Upgrade schema."""
    # Normalize existing values before adding strict constraints.
    op.execute(
        f"""
        UPDATE tenants
        SET plan = 'free_trial'
        WHERE plan IS NULL
           OR plan NOT IN {ALLOWED_TIERS_SQL}
        """
    )
    op.execute(
        f"""
        UPDATE tenant_subscriptions
        SET tier = 'free_trial'
        WHERE tier IS NULL
           OR tier NOT IN {ALLOWED_TIERS_SQL}
        """
    )

    op.alter_column(
        "tenants",
        "plan",
        existing_type=sa.String(),
        server_default=sa.text("'free_trial'"),
        existing_nullable=False,
    )
    op.alter_column(
        "tenant_subscriptions",
        "tier",
        existing_type=sa.String(length=20),
        server_default=sa.text("'free_trial'"),
        existing_nullable=False,
    )

    op.create_check_constraint(
        "ck_tenants_plan_allowed",
        "tenants",
        f"plan IN {ALLOWED_TIERS_SQL}",
    )
    op.create_check_constraint(
        "ck_tenant_subscriptions_tier_allowed",
        "tenant_subscriptions",
        f"tier IN {ALLOWED_TIERS_SQL}",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_tenant_subscriptions_tier_allowed", "tenant_subscriptions", type_="check")
    op.drop_constraint("ck_tenants_plan_allowed", "tenants", type_="check")

    op.execute("UPDATE tenant_subscriptions SET tier = 'trial' WHERE tier = 'free_trial'")
    op.execute("UPDATE tenants SET plan = 'trial' WHERE plan = 'free_trial'")

    op.alter_column(
        "tenant_subscriptions",
        "tier",
        existing_type=sa.String(length=20),
        server_default=sa.text("'trial'"),
        existing_nullable=False,
    )
    op.alter_column(
        "tenants",
        "plan",
        existing_type=sa.String(),
        server_default=sa.text("'trial'"),
        existing_nullable=False,
    )
