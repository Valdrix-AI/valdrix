"""add discovery candidates table

Revision ID: f2a9d7c6b5e4
Revises: 3d4e5f6a7b8c
Create Date: 2026-02-19 12:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a9d7c6b5e4"
down_revision = "3d4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="domain_dns"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("requires_admin_auth", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("connection_target", sa.String(length=32), nullable=True),
        sa.Column("connection_vendor_hint", sa.String(length=100), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "domain",
            "category",
            "provider",
            name="uq_discovery_candidate_tenant_domain_category_provider",
        ),
    )
    op.create_index(
        op.f("ix_discovery_candidates_tenant_id"),
        "discovery_candidates",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_domain"),
        "discovery_candidates",
        ["domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_category"),
        "discovery_candidates",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_provider"),
        "discovery_candidates",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_source"),
        "discovery_candidates",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_status"),
        "discovery_candidates",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_last_seen_at"),
        "discovery_candidates",
        ["last_seen_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_discovery_candidates_last_seen_at"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_status"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_source"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_provider"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_category"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_domain"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_tenant_id"), table_name="discovery_candidates")
    op.drop_table("discovery_candidates")
