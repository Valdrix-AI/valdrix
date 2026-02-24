"""add enforcement control plane tables

Revision ID: 7b9dd1cc2e61
Revises: 53d52a0a90e0
Create Date: 2026-02-22 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7b9dd1cc2e61"
down_revision: Union[str, Sequence[str], None] = "53d52a0a90e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENFORCEMENT_TABLES: tuple[str, ...] = (
    "enforcement_policies",
    "enforcement_budget_allocations",
    "enforcement_credit_grants",
    "enforcement_decisions",
    "enforcement_approval_requests",
)


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
        "enforcement_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "terraform_mode",
            sa.Enum(
                "shadow",
                "soft",
                "hard",
                name="enforcement_mode",
                native_enum=False,
            ),
            nullable=False,
            server_default=sa.text("'soft'"),
        ),
        sa.Column(
            "k8s_admission_mode",
            sa.Enum(
                "shadow",
                "soft",
                "hard",
                name="enforcement_mode",
                native_enum=False,
            ),
            nullable=False,
            server_default=sa.text("'soft'"),
        ),
        sa.Column(
            "require_approval_for_prod",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "require_approval_for_nonprod",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "auto_approve_below_monthly_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("25.0000"),
        ),
        sa.Column(
            "hard_deny_above_monthly_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("5000.0000"),
        ),
        sa.Column(
            "default_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("900"),
        ),
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.CheckConstraint(
            "default_ttl_seconds >= 60 AND default_ttl_seconds <= 86400",
            name="ck_enforcement_policy_ttl_bounds",
        ),
        sa.CheckConstraint(
            "auto_approve_below_monthly_usd >= 0",
            name="ck_enforcement_policy_auto_approve_non_negative",
        ),
        sa.CheckConstraint(
            "hard_deny_above_monthly_usd > 0",
            name="ck_enforcement_policy_hard_deny_positive",
        ),
        sa.CheckConstraint(
            "auto_approve_below_monthly_usd <= hard_deny_above_monthly_usd",
            name="ck_enforcement_policy_threshold_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_enforcement_policy_tenant"),
    )
    op.create_index(
        "ix_enforcement_policies_tenant_id",
        "enforcement_policies",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "enforcement_budget_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "scope_key",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column(
            "monthly_limit_usd",
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
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "monthly_limit_usd >= 0",
            name="ck_enforcement_budget_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "scope_key",
            name="uq_enforcement_budget_scope",
        ),
    )
    op.create_index(
        "ix_enforcement_budget_allocations_tenant_id",
        "enforcement_budget_allocations",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "enforcement_credit_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "scope_key",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column("total_amount_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("remaining_amount_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "total_amount_usd > 0",
            name="ck_enforcement_credit_total_positive",
        ),
        sa.CheckConstraint(
            "remaining_amount_usd >= 0",
            name="ck_enforcement_credit_remaining_non_negative",
        ),
        sa.CheckConstraint(
            "remaining_amount_usd <= total_amount_usd",
            name="ck_enforcement_credit_remaining_lte_total",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_enforcement_credit_grants_tenant_id",
        "enforcement_credit_grants",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_credit_scope_active_expiry",
        "enforcement_credit_grants",
        ["tenant_id", "scope_key", "active", "expires_at"],
        unique=False,
    )

    op.create_table(
        "enforcement_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.Column(
            "project_id",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
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
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "response_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("estimated_monthly_delta_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column(
            "estimated_hourly_delta_usd",
            sa.Numeric(14, 6),
            nullable=False,
            server_default=sa.text("0.000000"),
        ),
        sa.Column("allocation_available_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("credits_available_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column(
            "reserved_allocation_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0.0000"),
        ),
        sa.Column(
            "reserved_credit_usd",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0.0000"),
        ),
        sa.Column(
            "reservation_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "approval_token_issued",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "estimated_monthly_delta_usd >= 0",
            name="ck_enforcement_decision_monthly_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_hourly_delta_usd >= 0",
            name="ck_enforcement_decision_hourly_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_allocation_usd >= 0",
            name="ck_enforcement_decision_reserved_allocation_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_credit_usd >= 0",
            name="ck_enforcement_decision_reserved_credit_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source",
            "idempotency_key",
            name="uq_enforcement_decision_idempotency",
        ),
    )
    op.create_index(
        "ix_enforcement_decisions_tenant_id",
        "enforcement_decisions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decisions_source",
        "enforcement_decisions",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decisions_environment",
        "enforcement_decisions",
        ["environment"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decisions_decision",
        "enforcement_decisions",
        ["decision"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decisions_request_fingerprint",
        "enforcement_decisions",
        ["request_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decisions_created_at",
        "enforcement_decisions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_decision_tenant_created",
        "enforcement_decisions",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "enforcement_approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "denied",
                "expired",
                "cancelled",
                name="enforcement_approval_status",
                native_enum=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_notes", sa.String(length=1000), nullable=True),
        sa.Column("approval_token_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "approval_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["enforcement_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", name="uq_enforcement_approval_decision"),
    )
    op.create_index(
        "ix_enforcement_approval_requests_tenant_id",
        "enforcement_approval_requests",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_approval_requests_decision_id",
        "enforcement_approval_requests",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_approval_requests_status",
        "enforcement_approval_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_approval_status_expires",
        "enforcement_approval_requests",
        ["status", "expires_at"],
        unique=False,
    )

    for table_name in ENFORCEMENT_TABLES:
        _enable_rls_with_tenant_policy(table_name)


def downgrade() -> None:
    for table_name in ENFORCEMENT_TABLES:
        op.execute(
            f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}"
        )

    op.drop_index(
        "ix_enforcement_approval_status_expires",
        table_name="enforcement_approval_requests",
    )
    op.drop_index(
        "ix_enforcement_approval_requests_status",
        table_name="enforcement_approval_requests",
    )
    op.drop_index(
        "ix_enforcement_approval_requests_decision_id",
        table_name="enforcement_approval_requests",
    )
    op.drop_index(
        "ix_enforcement_approval_requests_tenant_id",
        table_name="enforcement_approval_requests",
    )
    op.drop_table("enforcement_approval_requests")

    op.drop_index(
        "ix_enforcement_decision_tenant_created",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_created_at",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_request_fingerprint",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_decision",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_environment",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_source",
        table_name="enforcement_decisions",
    )
    op.drop_index(
        "ix_enforcement_decisions_tenant_id",
        table_name="enforcement_decisions",
    )
    op.drop_table("enforcement_decisions")

    op.drop_index(
        "ix_enforcement_credit_scope_active_expiry",
        table_name="enforcement_credit_grants",
    )
    op.drop_index(
        "ix_enforcement_credit_grants_tenant_id",
        table_name="enforcement_credit_grants",
    )
    op.drop_table("enforcement_credit_grants")

    op.drop_index(
        "ix_enforcement_budget_allocations_tenant_id",
        table_name="enforcement_budget_allocations",
    )
    op.drop_table("enforcement_budget_allocations")

    op.drop_index(
        "ix_enforcement_policies_tenant_id",
        table_name="enforcement_policies",
    )
    op.drop_table("enforcement_policies")

