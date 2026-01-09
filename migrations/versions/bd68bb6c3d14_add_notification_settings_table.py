"""add_notification_settings_table

Revision ID: bd68bb6c3d14
Revises: eaf560eb3a89
Create Date: 2026-01-09 12:24:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd68bb6c3d14'
down_revision: Union[str, Sequence[str], None] = 'eaf560eb3a89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notification_settings table."""
    op.create_table(
        'notification_settings',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('slack_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('slack_channel_override', sa.String(64), nullable=True),
        sa.Column('digest_schedule', sa.String(20), nullable=False, server_default='daily'),
        sa.Column('digest_hour', sa.Integer(), nullable=False, server_default='9'),
        sa.Column('digest_minute', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('alert_on_budget_warning', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('alert_on_budget_exceeded', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('alert_on_zombie_detected', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id'),  # One settings per tenant
    )
    
    op.create_index('ix_notification_settings_tenant_id', 'notification_settings', ['tenant_id'])


def downgrade() -> None:
    """Drop notification_settings table."""
    op.drop_index('ix_notification_settings_tenant_id')
    op.drop_table('notification_settings')
