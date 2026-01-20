"""
Add Anomaly Markers Table for Forecast Tuning

Allows customers to mark expected anomalies (Black Friday, batch jobs)
so forecasting can exclude them during training.

Revision ID: i3j4k5l6m7n8
Revises: 2c3cc39a7285
Create Date: 2026-01-19

Phase 3.2: Manual intervention markers for forecast tuning.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'i3j4k5l6m7n8'
down_revision = '2c3cc39a7285'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'anomaly_markers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('start_date', sa.Date(), nullable=False, index=True),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('marker_type', sa.String(50), nullable=False, default='EXPECTED_SPIKE'),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('service_filter', sa.String(255), nullable=True),
        sa.Column('exclude_from_training', sa.Boolean(), default=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Add index for date range queries
    op.create_index(
        'ix_anomaly_markers_date_range',
        'anomaly_markers',
        ['tenant_id', 'start_date', 'end_date']
    )


def downgrade() -> None:
    op.drop_index('ix_anomaly_markers_date_range', table_name='anomaly_markers')
    op.drop_table('anomaly_markers')
