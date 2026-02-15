"""add policy config and escalation state

Revision ID: c4f5d6e7a8b9
Revises: 9c27f5a6b2d4
Create Date: 2026-02-12 20:16:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f5d6e7a8b9"
down_revision: Union[str, Sequence[str], None] = "9c27f5a6b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remediation_settings",
        sa.Column("policy_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_block_production_destructive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_require_gpu_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_low_confidence_warn_threshold",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.90",
        ),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_violation_notify_slack",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_violation_notify_jira",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "remediation_settings",
        sa.Column(
            "policy_escalation_required_role",
            sa.String(length=20),
            nullable=False,
            server_default="owner",
        ),
    )

    op.add_column(
        "remediation_requests",
        sa.Column("escalation_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("escalation_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_remediation_requests_escalation_required"),
        "remediation_requests",
        ["escalation_required"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_remediation_requests_escalation_required"), table_name="remediation_requests")
    op.drop_column("remediation_requests", "escalated_at")
    op.drop_column("remediation_requests", "escalation_reason")
    op.drop_column("remediation_requests", "escalation_required")

    op.drop_column("remediation_settings", "policy_escalation_required_role")
    op.drop_column("remediation_settings", "policy_violation_notify_jira")
    op.drop_column("remediation_settings", "policy_violation_notify_slack")
    op.drop_column("remediation_settings", "policy_low_confidence_warn_threshold")
    op.drop_column("remediation_settings", "policy_require_gpu_override")
    op.drop_column("remediation_settings", "policy_block_production_destructive")
    op.drop_column("remediation_settings", "policy_enabled")
