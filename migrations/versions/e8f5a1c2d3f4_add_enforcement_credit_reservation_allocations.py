"""add enforcement credit reservation allocations table

Revision ID: e8f5a1c2d3f4
Revises: c3f8d9e4a1b2
Create Date: 2026-02-24 17:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f5a1c2d3f4"
down_revision: Union[str, Sequence[str], None] = "c3f8d9e4a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_rls_with_tenant_policy(table_name: str) -> None:
    policy_name = f"{table_name}_tenant_isolation"
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    op.execute(
        f"""
        CREATE POLICY {policy_name}
        ON {table_name}
        USING (
            tenant_id = (
                SELECT current_setting('app.current_tenant_id', TRUE)::uuid
            )
        )
        WITH CHECK (
            tenant_id = (
                SELECT current_setting('app.current_tenant_id', TRUE)::uuid
            )
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "enforcement_credit_reservation_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("credit_grant_id", sa.Uuid(), nullable=False),
        sa.Column("reserved_amount_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column(
            "consumed_amount_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0.0000"),
        ),
        sa.Column(
            "released_amount_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0.0000"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reserved_amount_usd > 0",
            name="ck_enforcement_credit_reservation_reserved_positive",
        ),
        sa.CheckConstraint(
            "consumed_amount_usd >= 0",
            name="ck_enforcement_credit_reservation_consumed_non_negative",
        ),
        sa.CheckConstraint(
            "released_amount_usd >= 0",
            name="ck_enforcement_credit_reservation_released_non_negative",
        ),
        sa.CheckConstraint(
            "consumed_amount_usd + released_amount_usd <= reserved_amount_usd",
            name="ck_enforcement_credit_reservation_consumed_released_lte_reserved",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["enforcement_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["credit_grant_id"],
            ["enforcement_credit_grants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            "credit_grant_id",
            name="uq_enforcement_credit_reservation_decision_grant",
        ),
    )
    op.create_index(
        "ix_enforcement_credit_reservation_allocations_tenant_id",
        "enforcement_credit_reservation_allocations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_credit_reservation_allocations_decision_id",
        "enforcement_credit_reservation_allocations",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_credit_reservation_allocations_credit_grant_id",
        "enforcement_credit_reservation_allocations",
        ["credit_grant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_credit_reservation_allocations_active",
        "enforcement_credit_reservation_allocations",
        ["active"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_credit_reservation_tenant_active",
        "enforcement_credit_reservation_allocations",
        ["tenant_id", "active"],
        unique=False,
    )

    if op.get_bind().dialect.name == "postgresql":
        _enable_rls_with_tenant_policy("enforcement_credit_reservation_allocations")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS enforcement_credit_reservation_allocations_tenant_isolation ON enforcement_credit_reservation_allocations"
        )

    op.drop_index(
        "ix_enforcement_credit_reservation_tenant_active",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_index(
        "ix_enforcement_credit_reservation_allocations_active",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_index(
        "ix_enforcement_credit_reservation_allocations_credit_grant_id",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_index(
        "ix_enforcement_credit_reservation_allocations_decision_id",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_index(
        "ix_enforcement_credit_reservation_allocations_tenant_id",
        table_name="enforcement_credit_reservation_allocations",
    )
    op.drop_table("enforcement_credit_reservation_allocations")

