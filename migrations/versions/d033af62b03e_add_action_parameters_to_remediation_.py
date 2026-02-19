"""add action parameters to remediation requests

Revision ID: d033af62b03e
Revises: c9d0e1f2a3b4
Create Date: 2026-02-19 01:27:28.497646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd033af62b03e'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('remediation_requests', sa.Column('action_parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('remediation_requests', 'action_parameters')
