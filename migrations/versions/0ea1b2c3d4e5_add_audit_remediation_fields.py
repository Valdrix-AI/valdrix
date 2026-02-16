"""Add audit remediation fields: priority, expires_at, rotated_at

Revision ID: 0ea1b2c3d4e5
Revises: 844ca0dfb7a7
Create Date: 2026-01-18 19:50:00.000000

BE-SCHED-5: Add priority field to background_jobs
BE-CONN-2: Add expires_at to oidc_keys for key rotation
BE-CONN-3: Add rotated_at to oidc_keys for dual-key support
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0ea1b2c3d4e5'
down_revision = '844ca0dfb7a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # BE-SCHED-5: Add priority field to background_jobs
    if 'background_jobs' in tables:
        cols = [c['name'] for c in inspector.get_columns('background_jobs')]
        if 'priority' not in cols:
            op.add_column(
                'background_jobs',
                sa.Column('priority', sa.Integer(), nullable=False, server_default='0')
            )
            op.create_index(
                'ix_background_jobs_priority',
                'background_jobs',
                ['priority'],
                unique=False
            )
    
    # BE-CONN-2/3: Add key rotation fields to oidc_keys
    if 'oidc_keys' in tables:
        cols = [c['name'] for c in inspector.get_columns('oidc_keys')]
        if 'expires_at' not in cols:
            op.add_column(
                'oidc_keys',
                sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True)
            )
        if 'rotated_at' not in cols:
            op.add_column(
                'oidc_keys',
                sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True)
            )
        
        # Backfill existing keys with 30-day expiration from creation
        op.execute("""
            UPDATE oidc_keys 
            SET expires_at = created_at + INTERVAL '30 days'
            WHERE expires_at IS NULL
        """)


def downgrade() -> None:
    # Remove key rotation fields
    op.drop_column('oidc_keys', 'rotated_at')
    op.drop_column('oidc_keys', 'expires_at')
    
    # Remove priority field
    op.drop_index('ix_background_jobs_priority', table_name='background_jobs')
    op.drop_column('background_jobs', 'priority')
