"""add enforcement action executions table

Revision ID: l8m9n0p1q2r3
Revises: k7l8m9n0p1q2
Create Date: 2026-02-25 08:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "l8m9n0p1q2r3"
down_revision: Union[str, Sequence[str], None] = "k7l8m9n0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _action_status_enum() -> sa.Enum:
    return sa.Enum(
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        name="enforcement_action_status",
        native_enum=False,
    )


def upgrade() -> None:
    op.create_table(
        "enforcement_action_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_reference", sa.String(length=512), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", _action_status_enum(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "retry_backoff_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column("lease_ttl_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("locked_by_worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=1000), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name="ck_enforcement_action_max_attempts_ge_1",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_enforcement_action_attempt_count_ge_0",
        ),
        sa.CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_enforcement_action_attempt_count_lte_max",
        ),
        sa.CheckConstraint(
            "retry_backoff_seconds >= 1 AND retry_backoff_seconds <= 86400",
            name="ck_enforcement_action_retry_backoff_bounds",
        ),
        sa.CheckConstraint(
            "lease_ttl_seconds >= 30 AND lease_ttl_seconds <= 3600",
            name="ck_enforcement_action_lease_ttl_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["enforcement_approval_requests.id"],
            ondelete="SET NULL",
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
        sa.UniqueConstraint(
            "tenant_id",
            "decision_id",
            "action_type",
            "idempotency_key",
            name="uq_enforcement_action_idempotency",
        ),
    )
    op.create_index(
        "ix_enforcement_action_executions_tenant_id",
        "enforcement_action_executions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_executions_decision_id",
        "enforcement_action_executions",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_executions_approval_request_id",
        "enforcement_action_executions",
        ["approval_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_executions_status",
        "enforcement_action_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_executions_next_retry_at",
        "enforcement_action_executions",
        ["next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_retry_queue",
        "enforcement_action_executions",
        ["tenant_id", "status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_enforcement_action_decision_created",
        "enforcement_action_executions",
        ["decision_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_enforcement_action_decision_created",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_retry_queue",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_executions_next_retry_at",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_executions_status",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_executions_approval_request_id",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_executions_decision_id",
        table_name="enforcement_action_executions",
    )
    op.drop_index(
        "ix_enforcement_action_executions_tenant_id",
        table_name="enforcement_action_executions",
    )
    op.drop_table("enforcement_action_executions")
