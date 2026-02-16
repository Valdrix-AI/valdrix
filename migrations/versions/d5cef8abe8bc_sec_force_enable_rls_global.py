"""sec_force_enable_rls_global

Revision ID: d5cef8abe8bc
Revises: 3741a713f494
Create Date: 2026-02-15 10:39:21.296085

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5cef8abe8bc'
down_revision: Union[str, Sequence[str], None] = '3741a713f494'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Force enable RLS on sensitive application tables."""
    tables = [
        "aws_connections",
        "azure_connections",
        "gcp_connections",
        "tenants",
        "background_jobs",
        "cost_records",
        "cost_allocations",
        "remediation_requests",
        "remediation_settings",
        "discovered_accounts",
        "cloud_accounts",
        "strategy_recommendations",
        "optimization_strategies",
        "notification_settings",
        "audit_logs",
        "llm_budgets",
        "llm_usage",
        "carbon_settings",
        "realized_savings_events",
    ]
    for table in tables:
        # Check if table exists first to avoid errors during CI or partial environments
        op.execute(f"ALTER TABLE IF EXISTS {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable RLS for rollback."""
    tables = [
        "aws_connections",
        "azure_connections",
        "gcp_connections",
        "tenants",
        "background_jobs",
        "cost_records",
        "cost_allocations",
        "remediation_requests",
        "remediation_settings",
        "discovered_accounts",
        "cloud_accounts",
        "strategy_recommendations",
        "optimization_strategies",
        "notification_settings",
        "audit_logs",
        "llm_budgets",
        "llm_usage",
        "carbon_settings",
        "realized_savings_events",
    ]
    for table in tables:
        op.execute(f"ALTER TABLE IF EXISTS {table} DISABLE ROW LEVEL SECURITY")
