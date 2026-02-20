"""add cloud account production profile fields

Revision ID: 9f7a6b5c4d3e
Revises: f2a9d7c6b5e4
Create Date: 2026-02-20 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f7a6b5c4d3e"
down_revision = "f2a9d7c6b5e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cloud_accounts",
        sa.Column("is_production", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("criticality", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_cloud_accounts_is_production"),
        "cloud_accounts",
        ["is_production"],
        unique=False,
    )
    op.alter_column("cloud_accounts", "is_production", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_cloud_accounts_is_production"), table_name="cloud_accounts")
    op.drop_column("cloud_accounts", "criticality")
    op.drop_column("cloud_accounts", "is_production")
