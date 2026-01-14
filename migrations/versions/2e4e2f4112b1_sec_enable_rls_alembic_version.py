"""sec_enable_rls_alembic_version

Revision ID: 2e4e2f4112b1
Revises: 171defe4083a
Create Date: 2026-01-12 18:29:35.668522

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2e4e2f4112b1'
down_revision: Union[str, Sequence[str], None] = '171defe4083a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE alembic_version DISABLE ROW LEVEL SECURITY")
