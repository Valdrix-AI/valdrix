"""final merge of disparate heads

Revision ID: e43503516a27
Revises: bc12cd34ef56, e9f0a1b2c3d4
Create Date: 2026-02-15 08:22:20.393077

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'e43503516a27'
down_revision: Union[str, Sequence[str], None] = ('bc12cd34ef56', 'e9f0a1b2c3d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
