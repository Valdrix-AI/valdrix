"""add_cur_tracking_to_aws_connection

Revision ID: 5223a2091233
Revises: 87af6d57776b
Create Date: 2026-01-15 00:03:27.979667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5223a2091233'
down_revision: Union[str, Sequence[str], None] = '87af6d57776b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('aws_connections', sa.Column('cur_status', sa.String(length=20), server_default='none', nullable=False))
    op.add_column('aws_connections', sa.Column('cur_bucket_name', sa.String(length=255), nullable=True))
    op.add_column('aws_connections', sa.Column('cur_report_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('aws_connections', 'cur_report_name')
    op.drop_column('aws_connections', 'cur_bucket_name')
    op.drop_column('aws_connections', 'cur_status')
