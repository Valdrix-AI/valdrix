"""add api_secret to platform and hybrid connections

Revision ID: cd8320390f08
Revises: e1f2a3b4c5d6
Create Date: 2026-02-15 00:27:55.378647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd8320390f08'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("platform_connections", sa.Column("api_secret", sa.String(length=1024), nullable=True))
    op.add_column("hybrid_connections", sa.Column("api_secret", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("hybrid_connections", "api_secret")
    op.drop_column("platform_connections", "api_secret")
