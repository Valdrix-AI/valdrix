"""merge_heads_free_tier_cleanup

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f3, b0c1d2e3f4a5
Create Date: 2026-02-18 00:20:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = ("a7b8c9d0e1f3", "b0c1d2e3f4a5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
