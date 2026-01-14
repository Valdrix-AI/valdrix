"""sec_enable_rls_all_tables

Revision ID: b8cca4316ecf
Revises: f9d23abde562
Create Date: 2026-01-12 20:50:28.581687

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8cca4316ecf'
down_revision: Union[str, Sequence[str], None] = 'f9d23abde562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable RLS on all public schema tables for Supabase security."""
    tables = [
        "aws_connections",
        "carbon_settings",
        "cloud_accounts",
        "cost_records",
        "llm_budgets",
        "llm_usage",
        "notification_settings",
        "remediation_requests",
        "remediation_settings",
        "users",
    ]
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable RLS on all public schema tables."""
    tables = [
        "aws_connections",
        "carbon_settings",
        "cloud_accounts",
        "cost_records",
        "llm_budgets",
        "llm_usage",
        "notification_settings",
        "remediation_requests",
        "remediation_settings",
        "users",
    ]
    for table in tables:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
