"""merge multi_cloud and background_jobs

Revision ID: f62cfab1b4fd
Revises: 369c1a3ca0d4, f5g6h7i8j9k0
Create Date: 2026-01-15 11:04:51.343110

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'f62cfab1b4fd'
down_revision: Union[str, Sequence[str], None] = ('369c1a3ca0d4', 'f5g6h7i8j9k0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
