"""add_hourly_timestamp_to_cost_records

Revision ID: 00d34fc44365
Revises: 5223a2091233
Create Date: 2026-01-15 00:36:38.339991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00d34fc44365'
down_revision: Union[str, Sequence[str], None] = '5223a2091233'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new timestamp column (Expand phase)
    op.add_column('cost_records', sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_cost_records_timestamp'), 'cost_records', ['timestamp'], unique=False)
    
    # 2. Backfill data from the old 'recorded_at' Date column
    # Use raw SQL for the cross-type update
    op.execute("UPDATE cost_records SET timestamp = recorded_at::timestamp AT TIME ZONE 'UTC' WHERE timestamp IS NULL")

def downgrade() -> None:
    op.drop_index(op.f('ix_cost_records_timestamp'), table_name='cost_records')
    op.drop_column('cost_records', 'timestamp')
