"""Add SSO federation fields to tenant identity settings.

Revision ID: e9f0a1b2c3d4
Revises: e0f1a2b3c4d5
Create Date: 2026-02-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_identity_settings",
        sa.Column("sso_federation_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "tenant_identity_settings",
        sa.Column("sso_federation_mode", sa.String(length=32), nullable=False, server_default="domain"),
    )
    op.add_column(
        "tenant_identity_settings",
        sa.Column("sso_federation_provider_id", sa.String(length=255), nullable=True),
    )

    op.alter_column("tenant_identity_settings", "sso_federation_enabled", server_default=None)
    op.alter_column("tenant_identity_settings", "sso_federation_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("tenant_identity_settings", "sso_federation_provider_id")
    op.drop_column("tenant_identity_settings", "sso_federation_mode")
    op.drop_column("tenant_identity_settings", "sso_federation_enabled")
