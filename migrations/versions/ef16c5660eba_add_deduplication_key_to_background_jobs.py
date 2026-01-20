"""add deduplication_key to background_jobs

Revision ID: ef16c5660eba
Revises: i3j4k5l6m7n8
Create Date: 2026-01-19 17:31:14.452989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef16c5660eba'
down_revision: Union[str, Sequence[str], None] = 'i3j4k5l6m7n8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add deduplication_key to background_jobs
    op.add_column('background_jobs', sa.Column('deduplication_key', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_background_jobs_deduplication_key'), 'background_jobs', ['deduplication_key'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_background_jobs_deduplication_key'), table_name='background_jobs')
    op.drop_column('background_jobs', 'deduplication_key')
