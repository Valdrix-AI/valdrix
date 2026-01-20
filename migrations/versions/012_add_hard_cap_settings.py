"""add hard cap settings

Revision ID: 012_add_hard_cap_settings
Revises: fbf7685b0e3c
Create Date: 2026-01-18 17:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012_add_hard_cap_settings'
down_revision = 'fbf7685b0e3c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('remediation_settings', sa.Column('hard_cap_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('remediation_settings', sa.Column('monthly_hard_cap_usd', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'))


def downgrade() -> None:
    op.drop_column('remediation_settings', 'monthly_hard_cap_usd')
    op.drop_column('remediation_settings', 'hard_cap_enabled')
