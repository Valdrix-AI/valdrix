"""add enforcement approval routing policy and trace fields

Revision ID: f3c4d5e6a7b8
Revises: e8f5a1c2d3f4
Create Date: 2026-02-24 22:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c4d5e6a7b8"
down_revision: Union[str, Sequence[str], None] = "e8f5a1c2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_array_server_default() -> sa.TextClause:
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def _json_object_server_default() -> sa.TextClause:
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def upgrade() -> None:
    op.add_column(
        "enforcement_policies",
        sa.Column(
            "enforce_prod_requester_reviewer_separation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column(
            "enforce_nonprod_requester_reviewer_separation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column(
            "approval_routing_rules",
            sa.JSON(),
            nullable=False,
            server_default=_json_array_server_default(),
        ),
    )

    op.add_column(
        "enforcement_approval_requests",
        sa.Column("routing_rule_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "enforcement_approval_requests",
        sa.Column(
            "routing_trace",
            sa.JSON(),
            nullable=False,
            server_default=_json_object_server_default(),
        ),
    )

    op.alter_column(
        "enforcement_policies",
        "enforce_prod_requester_reviewer_separation",
        server_default=None,
    )
    op.alter_column(
        "enforcement_policies",
        "enforce_nonprod_requester_reviewer_separation",
        server_default=None,
    )
    op.alter_column(
        "enforcement_policies",
        "approval_routing_rules",
        server_default=None,
    )
    op.alter_column(
        "enforcement_approval_requests",
        "routing_trace",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("enforcement_approval_requests", "routing_trace")
    op.drop_column("enforcement_approval_requests", "routing_rule_id")
    op.drop_column("enforcement_policies", "approval_routing_rules")
    op.drop_column("enforcement_policies", "enforce_nonprod_requester_reviewer_separation")
    op.drop_column("enforcement_policies", "enforce_prod_requester_reviewer_separation")
