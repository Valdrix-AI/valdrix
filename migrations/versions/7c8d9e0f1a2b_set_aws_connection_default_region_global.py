"""set aws connection default region to global

Revision ID: 7c8d9e0f1a2b
Revises: 6a1b2c3d4e5f
Create Date: 2026-02-20 11:15:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c8d9e0f1a2b"
down_revision: Union[str, Sequence[str], None] = "6a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE aws_connections ALTER COLUMN region SET DEFAULT 'global'")


def downgrade() -> None:
    op.execute("ALTER TABLE aws_connections ALTER COLUMN region SET DEFAULT 'us-east-1'")
