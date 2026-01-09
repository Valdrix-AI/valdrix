"""add_aws_connections_table

Revision ID: eaf560eb3a89
Revises: 58130c25a4ca
Create Date: 2026-01-09 07:07:36.576598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eaf560eb3a89'
down_revision: Union[str, Sequence[str], None] = '58130c25a4ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create aws_connections table."""
    op.create_table(
        'aws_connections',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('aws_account_id', sa.String(12), nullable=False),
        sa.Column('role_arn', sa.String(255), nullable=False),
        sa.Column('external_id', sa.String(64), nullable=False),
        sa.Column('region', sa.String(32), nullable=False, server_default='us-east-1'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for faster lookups
    op.create_index('ix_aws_connections_tenant_id', 'aws_connections', ['tenant_id'])
    op.create_index('ix_aws_connections_aws_account_id', 'aws_connections', ['aws_account_id'])


def downgrade() -> None:
    """Drop aws_connections table."""
    op.drop_index('ix_aws_connections_aws_account_id')
    op.drop_index('ix_aws_connections_tenant_id')
    op.drop_table('aws_connections')

