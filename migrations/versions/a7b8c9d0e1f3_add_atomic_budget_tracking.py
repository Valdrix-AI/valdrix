"""add atomic budget tracking

Revision ID: a7b8c9d0e1f3
Revises: e43503516a27
Create Date: 2026-02-17 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f3'
down_revision = 'e43503516a27'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add atomic tracking columns to llm_budgets
    op.add_column('llm_budgets', sa.Column('monthly_spend_usd', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0.0'))
    op.add_column('llm_budgets', sa.Column('pending_reservations_usd', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0.0'))
    op.add_column('llm_budgets', sa.Column('budget_reset_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    # 2. Update existing budgets to have valid reset_at (start of current month)
    # This ensures month-rollover logic in budget_manager.py works correctly from day one.
    op.execute("UPDATE llm_budgets SET budget_reset_at = date_trunc('month', now())")

def downgrade() -> None:
    op.drop_column('llm_budgets', 'budget_reset_at')
    op.drop_column('llm_budgets', 'pending_reservations_usd')
    op.drop_column('llm_budgets', 'monthly_spend_usd')
