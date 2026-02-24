"""add enforcement approval token consumed timestamp

Revision ID: 84a6f82e9a14
Revises: 7b9dd1cc2e61
Create Date: 2026-02-22 22:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "84a6f82e9a14"
down_revision: Union[str, Sequence[str], None] = "7b9dd1cc2e61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enforcement_approval_requests",
        sa.Column("approval_token_consumed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enforcement_approval_requests", "approval_token_consumed_at")
