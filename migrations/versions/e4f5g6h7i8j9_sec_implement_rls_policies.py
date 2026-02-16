"""sec_implement_rls_policies

Revision ID: e4f5g6h7i8j9
Revises: b8cca4316ecf
Create Date: 2026-01-14 21:45:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4f5g6h7i8j9'
down_revision: Union[str, Sequence[str], None] = 'b8cca4316ecf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Implement RLS policies for all tenant-related tables."""
    
    # 1. Tenants Table (Self-isolation)
    # Optimization: Using subquery for current_setting to prevent re-evaluation
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON tenants
        USING (id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
    """)

    # 2. General Tenant-Scoped Tables
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
        # Optimization: Wrapping current_setting in a SELECT subquery for performance
        op.execute(f"""
            CREATE POLICY {table}_isolation_policy ON {table}
            USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
        """)


def downgrade() -> None:
    """Drop RLS policies."""
    
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON tenants")
    
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
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation_policy ON {table}")
