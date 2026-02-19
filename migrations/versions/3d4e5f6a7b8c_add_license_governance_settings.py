"""add license governance fields to remediation settings

Revision ID: 3d4e5f6a7b8c
Revises: e6f7a8b9c0d1
Create Date: 2026-02-19 08:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3d4e5f6a7b8c'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('remediation_settings', sa.Column('license_auto_reclaim_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('remediation_settings', sa.Column('license_inactive_threshold_days', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('remediation_settings', sa.Column('license_reclaim_grace_period_days', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('remediation_settings', sa.Column('license_downgrade_recommendations_enabled', sa.Boolean(), nullable=False, server_default='true'))

def downgrade():
    op.drop_column('remediation_settings', 'license_downgrade_recommendations_enabled')
    op.drop_column('remediation_settings', 'license_reclaim_grace_period_days')
    op.drop_column('remediation_settings', 'license_inactive_threshold_days')
    op.drop_column('remediation_settings', 'license_auto_reclaim_enabled')
