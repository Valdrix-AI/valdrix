"""Add persisted cloud resource pricing catalog.

Revision ID: n0p1q2r3s4t5
Revises: m9n0p1q2r3s4
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "n0p1q2r3s4t5"
down_revision = "m9n0p1q2r3s4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_resource_pricing",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_size", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("hourly_rate_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "resource_type",
            "resource_size",
            "region",
            name="uq_cloud_resource_pricing_catalog_key",
        ),
    )
    op.create_index(
        op.f("ix_cloud_resource_pricing_provider"),
        "cloud_resource_pricing",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cloud_resource_pricing_resource_type"),
        "cloud_resource_pricing",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cloud_resource_pricing_resource_size"),
        "cloud_resource_pricing",
        ["resource_size"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cloud_resource_pricing_region"),
        "cloud_resource_pricing",
        ["region"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cloud_resource_pricing_region"), table_name="cloud_resource_pricing")
    op.drop_index(
        op.f("ix_cloud_resource_pricing_resource_size"),
        table_name="cloud_resource_pricing",
    )
    op.drop_index(
        op.f("ix_cloud_resource_pricing_resource_type"),
        table_name="cloud_resource_pricing",
    )
    op.drop_index(op.f("ix_cloud_resource_pricing_provider"), table_name="cloud_resource_pricing")
    op.drop_table("cloud_resource_pricing")
