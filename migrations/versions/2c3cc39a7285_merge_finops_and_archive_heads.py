"""merge_finops_and_archive_heads

Revision ID: 2c3cc39a7285
Revises: 2e3ca98ca84e, h2i3j4k5l6m7
Create Date: 2026-01-19 16:55:57.596884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c3cc39a7285'
down_revision: Union[str, Sequence[str], None] = ('2e3ca98ca84e', 'h2i3j4k5l6m7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
