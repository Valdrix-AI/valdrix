"""Add SCIM group mappings to tenant identity settings.

Revision ID: d8e9f0a1b2c3
Revises: c6d7e8f9a0b1
Create Date: 2026-02-14

This adds a DB-backed list of SCIM group mappings so tenants can map IdP groups
to Valdrix roles/personas deterministically (Enterprise packaging hardening).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c3"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_identity_settings",
        sa.Column(
            "scim_group_mappings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_identity_settings", "scim_group_mappings")

