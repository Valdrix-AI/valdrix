"""add enforcement ledger approval linkage fields

Revision ID: j6k7l8m9n0p1
Revises: i5j6k7l8m9n0
Create Date: 2026-02-25 02:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "j6k7l8m9n0p1"
down_revision: Union[str, Sequence[str], None] = "i5j6k7l8m9n0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _approval_status_enum() -> sa.Enum:
    return sa.Enum(
        "pending",
        "approved",
        "denied",
        "expired",
        name="enforcement_approval_status",
        native_enum=False,
    )


def upgrade() -> None:
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column("approval_status", _approval_status_enum(), nullable=True),
    )
    op.create_index(
        "ix_enforcement_decision_ledger_approval_request_id",
        "enforcement_decision_ledger",
        ["approval_request_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_enforcement_decision_ledger_approval_request_id",
        "enforcement_decision_ledger",
        "enforcement_approval_requests",
        ["approval_request_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_enforcement_decision_ledger_approval_request_id",
        "enforcement_decision_ledger",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_enforcement_decision_ledger_approval_request_id",
        table_name="enforcement_decision_ledger",
    )
    op.drop_column("enforcement_decision_ledger", "approval_status")
    op.drop_column("enforcement_decision_ledger", "approval_request_id")
