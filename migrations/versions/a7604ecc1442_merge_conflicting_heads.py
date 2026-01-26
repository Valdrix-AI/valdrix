"""merge_conflicting_heads

Revision ID: a7604ecc1442
Revises: c5127e32a8b0, f8g9h0i1j2k3
Create Date: 2026-01-16 17:22:41.980379

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'a7604ecc1442'
down_revision: Union[str, Sequence[str], None] = ('c5127e32a8b0', 'f8g9h0i1j2k3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
