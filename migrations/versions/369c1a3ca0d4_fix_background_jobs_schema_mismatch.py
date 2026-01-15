"""fix_background_jobs_schema_mismatch

Revision ID: 369c1a3ca0d4
Revises: fbf7685b0e3c
Create Date: 2026-01-15 05:59:23.863019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '369c1a3ca0d4'
down_revision: Union[str, Sequence[str], None] = 'fbf7685b0e3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing updated_at column to background_jobs (it's in the Base model but was missing in migration)
    op.add_column('background_jobs', sa.Column('updated_at', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()'), nullable=False))


def downgrade() -> None:
    op.drop_column('background_jobs', 'updated_at')
