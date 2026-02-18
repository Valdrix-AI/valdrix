"""drop_trial_started_at_and_enforce_free_tier_defaults

Revision ID: b0c1d2e3f4a5
Revises: 216df0ff8cca
Create Date: 2026-02-18 00:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "216df0ff8cca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALLOWED_TIERS_SQL = "('free', 'starter', 'growth', 'pro', 'enterprise')"


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns(table_name)
    )


def _set_default(
    *,
    table_name: str,
    column_name: str,
    default_value: str,
    existing_type: sa.types.TypeEngine,
) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT '{default_value}'"
        )
        return
    op.alter_column(
        table_name,
        column_name,
        existing_type=existing_type,
        server_default=sa.text(f"'{default_value}'"),
    )


def _recreate_allowed_tier_constraint(
    *,
    table_name: str,
    constraint_name: str,
    column_name: str,
) -> None:
    bind = op.get_bind()
    sqltext = f"{column_name} IN {ALLOWED_TIERS_SQL}"
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}")
    else:
        try:
            op.drop_constraint(constraint_name, table_name, type_="check")
        except Exception:
            # Legacy environments may not have this named constraint.
            pass

    op.create_check_constraint(
        constraint_name,
        table_name,
        sqltext,
    )


def _drop_column_check_constraints(
    *,
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    preferred_names: tuple[str, ...] = (),
) -> None:
    """Drop check constraints tied to a specific column before data normalization."""
    bind = op.get_bind()
    dropped: set[str] = set()

    # First drop explicitly known names (fast path, deterministic).
    for constraint_name in preferred_names:
        if not constraint_name:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(
                f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"
            )
        else:
            try:
                op.drop_constraint(constraint_name, table_name, type_="check")
            except Exception:
                pass
        dropped.add(constraint_name)

    # Then sweep any other check constraints that reference this column.
    for check in inspector.get_check_constraints(table_name):
        name = check.get("name")
        if not name or name in dropped:
            continue
        sqltext = str(check.get("sqltext", "")).lower()
        if column_name.lower() not in sqltext:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {name}")
        else:
            try:
                op.drop_constraint(name, table_name, type_="check")
            except Exception:
                pass


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "tenants"):
        _drop_column_check_constraints(
            inspector=inspector,
            table_name="tenants",
            column_name="plan",
            preferred_names=("ck_tenants_plan_allowed",),
        )
        op.execute(
            """
            UPDATE tenants
            SET plan = 'free'
            WHERE plan IS NULL
               OR plan IN ('trial', 'free_trial')
            """
        )
        _set_default(
            table_name="tenants",
            column_name="plan",
            default_value="free",
            existing_type=sa.String(),
        )
        _recreate_allowed_tier_constraint(
            table_name="tenants",
            constraint_name="ck_tenants_plan_allowed",
            column_name="plan",
        )

        if _column_exists(inspector, "tenants", "trial_started_at"):
            op.drop_column("tenants", "trial_started_at")

    if _table_exists(inspector, "tenant_subscriptions"):
        _drop_column_check_constraints(
            inspector=inspector,
            table_name="tenant_subscriptions",
            column_name="tier",
            preferred_names=("ck_tenant_subscriptions_tier_allowed",),
        )
        op.execute(
            """
            UPDATE tenant_subscriptions
            SET tier = 'free'
            WHERE tier IS NULL
               OR tier IN ('trial', 'free_trial')
            """
        )
        _set_default(
            table_name="tenant_subscriptions",
            column_name="tier",
            default_value="free",
            existing_type=sa.String(length=20),
        )
        _recreate_allowed_tier_constraint(
            table_name="tenant_subscriptions",
            constraint_name="ck_tenant_subscriptions_tier_allowed",
            column_name="tier",
        )


def downgrade() -> None:
    """Downgrade schema.

    Intentional policy: do not restore legacy trial/free_trial tier semantics.
    This only re-adds the removed nullable tracking column if needed.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "tenants") and not _column_exists(
        inspector, "tenants", "trial_started_at"
    ):
        op.add_column(
            "tenants",
            sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        )
