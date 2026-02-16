"""add provider invoices for close workflow

Revision ID: c6d7e8f9a0b1
Revises: b3c4d5e6f7a8
Create Date: 2026-02-14

Adds tenant-scoped provider invoice totals used for invoice-linked reconciliation
in the enterprise close workflow (reconciliation v3).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=8), nullable=False, server_default="0"),
        sa.Column(
            "total_amount_usd", sa.Numeric(precision=18, scale=8), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "period_start",
            "period_end",
            name="uix_provider_invoice_tenant_provider_period",
        ),
    )
    op.create_index("ix_provider_invoices_tenant_id", "provider_invoices", ["tenant_id"])
    op.create_index("ix_provider_invoices_provider", "provider_invoices", ["provider"])
    op.create_index(
        "ix_provider_invoices_period", "provider_invoices", ["period_start", "period_end"]
    )

    # RLS defense-in-depth. In tests/SQLite this is not executed.
    op.execute("ALTER TABLE provider_invoices ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_provider_invoices ON provider_invoices")
    op.execute(
        """
        CREATE POLICY tenant_isolation_provider_invoices ON provider_invoices
        USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
        """
    )


def downgrade() -> None:
    op.drop_index("ix_provider_invoices_period", table_name="provider_invoices")
    op.drop_index("ix_provider_invoices_provider", table_name="provider_invoices")
    op.drop_index("ix_provider_invoices_tenant_id", table_name="provider_invoices")
    op.drop_table("provider_invoices")

