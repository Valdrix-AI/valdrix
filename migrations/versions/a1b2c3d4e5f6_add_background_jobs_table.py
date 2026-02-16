"""
add background_jobs table for pg_cron scheduling

Revision ID: a1b2c3d4e5f6
Revises: 5037d41942b1
Create Date: 2026-01-14

This migration creates the background_jobs table for durable job processing.
Jobs survive app restarts and are processed by pg_cron.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '5037d41942b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table exists (it might have been created by a hardening migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'background_jobs' in inspector.get_table_names():
        print("Table 'background_jobs' already exists, skipping creation.")
        return

    # Create background_jobs table
    op.create_table(
        'background_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, 
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=True),
        sa.Column('result', postgresql.JSONB, nullable=True),
        sa.Column('attempts', sa.Integer, server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer, server_default='3', nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()'), nullable=False),
    )
    
    # Indexes for efficient job processing
    op.create_index(
        'ix_jobs_status_scheduled',
        'background_jobs',
        ['status', 'scheduled_for'],
        postgresql_where=sa.text("status = 'pending'")
    )
    op.create_index(
        'ix_jobs_tenant',
        'background_jobs',
        ['tenant_id']
    )
    op.create_index(
        'ix_jobs_type',
        'background_jobs',
        ['job_type']
    )
    
    # Enable RLS on background_jobs
    op.execute("ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY")
    
    # RLS policy: tenants can only see their own jobs
    op.execute("""
        CREATE POLICY background_jobs_tenant_isolation ON background_jobs
        FOR ALL
        USING (tenant_id = (SELECT current_setting('app.current_tenant_id', true)::uuid));
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS background_jobs_tenant_isolation ON background_jobs")
    op.drop_index('ix_jobs_type')
    op.drop_index('ix_jobs_tenant')
    op.drop_index('ix_jobs_status_scheduled')
    op.drop_table('background_jobs')
