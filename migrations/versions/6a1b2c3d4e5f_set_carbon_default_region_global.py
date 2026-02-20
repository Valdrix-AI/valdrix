"""set carbon settings default region to global

Revision ID: 6a1b2c3d4e5f
Revises: 9f7a6b5c4d3e
Create Date: 2026-02-20 13:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6a1b2c3d4e5f"
down_revision = "9f7a6b5c4d3e"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "carbon_settings",
        "default_region",
        existing_type=sa.String(),
        server_default=sa.text("'global'"),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "carbon_settings",
        "default_region",
        existing_type=sa.String(),
        server_default=sa.text("'us-east-1'"),
        existing_nullable=False,
    )

