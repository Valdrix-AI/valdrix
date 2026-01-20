"""merge_heads_audit_cleanup

Revision ID: 31a34604efe0
Revises: 013_remediation_grace_period, 0fb1c2d3e4f5
Create Date: 2026-01-19 02:34:13.535145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31a34604efe0'
down_revision: Union[str, Sequence[str], None] = ('013_remediation_grace_period', '0fb1c2d3e4f5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
