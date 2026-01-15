"""merge_heads

Revision ID: 87af6d57776b
Revises: a1b2c3d4e5f6, ab12cd34ef56
Create Date: 2026-01-15 00:01:57.105807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87af6d57776b'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'ab12cd34ef56')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
