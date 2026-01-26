"""enterprise_precision_migration

Revision ID: 1234567890ab
Revises: e4f5g6h7i8j9
Create Date: 2026-01-14 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1234567890ab'
down_revision = 'e4f5g6h7i8j9'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Alter cost_usd from Numeric(12, 4) to Numeric(18, 8) in cloud_accounts (if it existed) or other tables
    # But mainly CostRecord
    
    op.alter_column('cost_records', 'cost_usd',
               existing_type=sa.Numeric(precision=12, scale=4),
               type_=sa.Numeric(precision=18, scale=8),
               existing_nullable=True)

    op.alter_column('llm_usage', 'cost_usd',
               existing_type=sa.Numeric(precision=10, scale=6),
               type_=sa.Numeric(precision=18, scale=8),
               existing_nullable=False)

    # 2. Add multi-currency columns
    op.add_column('cost_records', sa.Column('amount_raw', sa.Numeric(precision=18, scale=8), nullable=True))
    op.add_column('cost_records', sa.Column('currency', sa.String(), nullable=True, server_default='USD'))

def downgrade() -> None:
    op.drop_column('cost_records', 'currency')
    op.drop_column('cost_records', 'amount_raw')
    
    op.alter_column('llm_usage', 'cost_usd',
               existing_type=sa.Numeric(precision=18, scale=8),
               type_=sa.Numeric(precision=10, scale=6),
               existing_nullable=False)
               
    op.alter_column('cost_records', 'cost_usd',
               existing_type=sa.Numeric(precision=18, scale=8),
               type_=sa.Numeric(precision=12, scale=4),
               existing_nullable=True)
