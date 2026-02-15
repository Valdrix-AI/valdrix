"""add remediation grace period

Revision ID: 013_remediation_grace_period
Revises: 012_add_hard_cap_settings
Create Date: 2026-01-18 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_remediation_grace_period'
down_revision = '012_add_hard_cap_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Add scheduled_execution_at column
    op.add_column('remediation_requests', sa.Column('scheduled_execution_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_remediation_requests_scheduled_execution_at'), 'remediation_requests', ['scheduled_execution_at'], unique=False)
    
    # Update RemediationStatus enum (PostgreSQL)
    # Note: Alembic doesn't natively support adding values to existing Enums easily across all DBs.
    # For PostgreSQL, we use ALTER TYPE.
    # Enum labels for this type are stored as member names (uppercase).
    op.execute("ALTER TYPE remediationstatus ADD VALUE IF NOT EXISTS 'SCHEDULED'")


def downgrade():
    op.drop_index(op.f('ix_remediation_requests_scheduled_execution_at'), table_name='remediation_requests')
    op.drop_column('remediation_requests', 'scheduled_execution_at')
    # Removing values from Enums is not supported in many DBs, so we usually leave the enum as is in downgrade.
