"""add_idempotency_constraint_to_costs

Revision ID: fbf7685b0e3c
Revises: 00d34fc44365
Create Date: 2026-01-15 05:48:35.300050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fbf7685b0e3c'
down_revision: Union[str, Sequence[str], None] = '00d34fc44365'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add usage_type column
    op.add_column('cost_records', sa.Column('usage_type', sa.String(), nullable=True))
    
    # 2. Add UniqueConstraint for idempotency (Phase 11)
    op.create_unique_constraint(
        'uix_account_cost_granularity', 
        'cost_records', 
        ['account_id', 'timestamp', 'service', 'region', 'usage_type']
    )


def downgrade() -> None:
    op.drop_constraint('uix_account_cost_granularity', 'cost_records', type_='unique')
    op.drop_column('cost_records', 'usage_type')
