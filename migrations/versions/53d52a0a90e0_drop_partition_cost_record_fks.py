"""drop partition cost record fks

Revision ID: 53d52a0a90e0
Revises: 99d8bf8028a2
Create Date: 2026-02-20 15:46:15.710584

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '53d52a0a90e0'
down_revision: Union[str, Sequence[str], None] = '99d8bf8028a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop partition-fragile FK constraints on cost rollup tables."""
    op.execute(
        "ALTER TABLE cost_allocations "
        "DROP CONSTRAINT IF EXISTS fk_cost_allocations_cost_record"
    )
    op.execute(
        "ALTER TABLE cost_audit_logs "
        "DROP CONSTRAINT IF EXISTS fk_cost_audit_logs_cost_record"
    )


def downgrade() -> None:
    """Best-effort restore of dropped constraints."""
    op.execute(
        "ALTER TABLE cost_allocations "
        "ADD CONSTRAINT fk_cost_allocations_cost_record "
        "FOREIGN KEY (cost_record_id, recorded_at) "
        "REFERENCES cost_records (id, recorded_at)"
    )
    op.execute(
        "ALTER TABLE cost_audit_logs "
        "ADD CONSTRAINT fk_cost_audit_logs_cost_record "
        "FOREIGN KEY (cost_record_id, cost_recorded_at) "
        "REFERENCES cost_records (id, recorded_at)"
    )
