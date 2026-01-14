"""sec_enable_rls_tenants

Revision ID: f9d23abde562
Revises: 2e4e2f4112b1
Create Date: 2026-01-12 20:36:50.272924

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f9d23abde562'
down_revision: Union[str, Sequence[str], None] = '2e4e2f4112b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")
