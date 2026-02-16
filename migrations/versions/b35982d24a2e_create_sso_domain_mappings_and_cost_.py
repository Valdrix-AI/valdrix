"""create sso_domain_mappings and cost_audit_logs

Revision ID: b35982d24a2e
Revises: e43503516a27
Create Date: 2026-02-15 09:32:48.359187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b35982d24a2e'
down_revision: Union[str, Sequence[str], None] = 'e43503516a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("sso_domain_mappings"):
        op.create_table(
            "sso_domain_mappings",
            sa.Column(
                "id",
                sa.Uuid(),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column(
                "federation_mode",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'domain'"),
            ),
            sa.Column("provider_id", sa.String(length=255), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("domain", name="uq_sso_domain_mappings_domain"),
        )
        op.create_index(
            "ix_sso_domain_mappings_tenant_id",
            "sso_domain_mappings",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            "ix_sso_domain_mappings_domain",
            "sso_domain_mappings",
            ["domain"],
            unique=False,
        )
        op.create_index(
            "ix_sso_domain_mappings_is_active",
            "sso_domain_mappings",
            ["is_active"],
            unique=False,
        )
        op.create_index(
            "ix_sso_domain_mappings_created_at",
            "sso_domain_mappings",
            ["created_at"],
            unique=False,
        )

    if not insp.has_table("cost_audit_logs"):
        op.create_table(
            "cost_audit_logs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("cost_record_id", sa.Uuid(), nullable=False),
            sa.Column("cost_recorded_at", sa.Date(), nullable=False),
            sa.Column("old_cost", sa.Numeric(precision=18, scale=8), nullable=False),
            sa.Column("new_cost", sa.Numeric(precision=18, scale=8), nullable=False),
            sa.Column(
                "reason",
                sa.String(),
                nullable=False,
                server_default=sa.text("'RESTATEMENT'"),
            ),
            sa.Column("ingestion_batch_id", sa.Uuid(), nullable=True),
            sa.Column(
                "recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["cost_record_id", "cost_recorded_at"],
                ["cost_records.id", "cost_records.recorded_at"],
                name="fk_cost_audit_logs_cost_record",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_cost_audit_logs_cost_record_id",
            "cost_audit_logs",
            ["cost_record_id"],
            unique=False,
        )
        op.create_index(
            "ix_cost_audit_logs_cost_recorded_at",
            "cost_audit_logs",
            ["cost_recorded_at"],
            unique=False,
        )
        op.create_index(
            "ix_cost_audit_logs_recorded_at",
            "cost_audit_logs",
            ["recorded_at"],
            unique=False,
        )
        op.create_index(
            "ix_cost_audit_logs_composite_record",
            "cost_audit_logs",
            ["cost_record_id", "cost_recorded_at"],
            unique=False,
        )
        op.create_index(
            "ix_cost_audit_logs_ingestion_batch_id",
            "cost_audit_logs",
            ["ingestion_batch_id"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("cost_audit_logs"):
        for idx in [
            "ix_cost_audit_logs_ingestion_batch_id",
            "ix_cost_audit_logs_recorded_at",
            "ix_cost_audit_logs_cost_recorded_at",
            "ix_cost_audit_logs_cost_record_id",
        ]:
            existing = {i["name"] for i in insp.get_indexes("cost_audit_logs")}
            if idx in existing:
                op.drop_index(idx, table_name="cost_audit_logs")
        op.drop_table("cost_audit_logs")

    if insp.has_table("sso_domain_mappings"):
        for idx in [
            "ix_sso_domain_mappings_created_at",
            "ix_sso_domain_mappings_is_active",
            "ix_sso_domain_mappings_domain",
            "ix_sso_domain_mappings_tenant_id",
        ]:
            existing = {i["name"] for i in insp.get_indexes("sso_domain_mappings")}
            if idx in existing:
                op.drop_index(idx, table_name="sso_domain_mappings")
        op.drop_table("sso_domain_mappings")
