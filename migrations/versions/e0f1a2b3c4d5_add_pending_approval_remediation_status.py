"""add pending_approval remediation status

Revision ID: e0f1a2b3c4d5
Revises: d7e8f9a0b1c2
Create Date: 2026-02-12 22:30:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "e0f1a2b3c4d5"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy persists Enum member names for this type (for example, PENDING),
    # so add the new member name and avoid positional AFTER dependency.
    op.execute("ALTER TYPE remediationstatus ADD VALUE IF NOT EXISTS 'PENDING_APPROVAL'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding the type.
    # Keep the new value on downgrade.
    pass
