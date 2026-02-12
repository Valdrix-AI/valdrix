"""Add connector config fields to Cloud+ connection tables.

Revision ID: 9c27f5a6b2d4
Revises: 8b9e4f2c6d1a
Create Date: 2026-02-12 09:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c27f5a6b2d4"
down_revision: Union[str, Sequence[str], None] = "8b9e4f2c6d1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "saas_connections",
        sa.Column(
            "connector_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "license_connections",
        sa.Column(
            "connector_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("saas_connections", "connector_config", server_default=None)
    op.alter_column("license_connections", "connector_config", server_default=None)


def downgrade() -> None:
    op.drop_column("license_connections", "connector_config")
    op.drop_column("saas_connections", "connector_config")
