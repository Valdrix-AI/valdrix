"""add enforcement decision ledger immutable table

Revision ID: c3f8d9e4a1b2
Revises: f2b9c0d4e8aa
Create Date: 2026-02-23 09:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3f8d9e4a1b2"
down_revision: Union[str, Sequence[str], None] = "f2b9c0d4e8aa"
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
        "enforcement_decision_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "terraform",
                "k8s_admission",
                "cloud_event",
                name="enforcement_source",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_reference", sa.String(length=512), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "ALLOW",
                "DENY",
                "REQUIRE_APPROVAL",
                "ALLOW_WITH_CREDITS",
                name="enforcement_decision_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason_codes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("estimated_monthly_delta_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("estimated_hourly_delta_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column(
            "reserved_total_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0.0000"),
        ),
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("request_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decision_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "estimated_monthly_delta_usd >= 0",
            name="ck_enforcement_ledger_monthly_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_hourly_delta_usd >= 0",
            name="ck_enforcement_ledger_hourly_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_total_usd >= 0",
            name="ck_enforcement_ledger_reserved_non_negative",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_enforcement_decision_ledger_tenant_id",
        "enforcement_decision_ledger",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decision_ledger_decision",
        "enforcement_decision_ledger",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decision_ledger_tenant_recorded",
        "enforcement_decision_ledger",
        ["tenant_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decision_ledger_recorded_at",
        "enforcement_decision_ledger",
        ["recorded_at"],
        unique=False,
    )

    if op.get_bind().dialect.name == "postgresql":
        _enable_rls_with_tenant_policy("enforcement_decision_ledger")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforcement_decision_ledger_immutable_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'enforcement_decision_ledger is append-only and immutable';
            END;
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER tr_enforcement_decision_ledger_immutable
            BEFORE UPDATE OR DELETE ON enforcement_decision_ledger
            FOR EACH ROW
            EXECUTE FUNCTION enforcement_decision_ledger_immutable_guard();
            """
        )
    elif op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER tr_enforcement_decision_ledger_no_update
            BEFORE UPDATE ON enforcement_decision_ledger
            BEGIN
                SELECT RAISE(FAIL, 'enforcement_decision_ledger is append-only and immutable');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER tr_enforcement_decision_ledger_no_delete
            BEFORE DELETE ON enforcement_decision_ledger
            BEGIN
                SELECT RAISE(FAIL, 'enforcement_decision_ledger is append-only and immutable');
            END;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS tr_enforcement_decision_ledger_immutable ON enforcement_decision_ledger"
        )
        op.execute("DROP FUNCTION IF EXISTS enforcement_decision_ledger_immutable_guard")
        op.execute(
            "DROP POLICY IF EXISTS enforcement_decision_ledger_tenant_isolation ON enforcement_decision_ledger"
        )
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS tr_enforcement_decision_ledger_no_update")
        op.execute("DROP TRIGGER IF EXISTS tr_enforcement_decision_ledger_no_delete")

    op.drop_index(
        "ix_enforcement_decision_ledger_recorded_at",
        table_name="enforcement_decision_ledger",
    )
    op.drop_index(
        "ix_enforcement_decision_ledger_tenant_recorded",
        table_name="enforcement_decision_ledger",
    )
    op.drop_index(
        "ix_enforcement_decision_ledger_decision",
        table_name="enforcement_decision_ledger",
    )
    op.drop_index(
        "ix_enforcement_decision_ledger_tenant_id",
        table_name="enforcement_decision_ledger",
    )
    op.drop_table("enforcement_decision_ledger")
