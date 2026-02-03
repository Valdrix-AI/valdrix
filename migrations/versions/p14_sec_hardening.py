"""Phase 14 Security Hardening: RLS Parity

Revision ID: p14_sec_hardening
Revises: 016_add_dunning_columns
Create Date: 2026-01-28

Enforces RLS isolation policies on remaining tables:
- anomaly_markers (Missing RLS and Policy)
- carbon_settings (Missing Policy)
- llm_budgets (Missing Policy)
- llm_usage (Missing Policy)
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'p14_sec_hardening'
down_revision = '016_add_dunning_columns'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Anomaly Markers (Needs RLS + Policy)
    op.execute("ALTER TABLE anomaly_markers ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY anomaly_markers_isolation_policy ON anomaly_markers
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)

    # 2. Carbon Settings (Needs Policy)
    op.execute("""
        CREATE POLICY carbon_settings_isolation_policy ON carbon_settings
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)

    # 3. LLM Budgets (Needs Policy)
    op.execute("""
        CREATE POLICY llm_budgets_isolation_policy ON llm_budgets
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)

    # 4. LLM Usage (Needs Policy)
    op.execute("""
        CREATE POLICY llm_usage_isolation_policy ON llm_usage
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS anomaly_markers_isolation_policy ON anomaly_markers")
    op.execute("DROP POLICY IF EXISTS carbon_settings_isolation_policy ON carbon_settings")
    op.execute("DROP POLICY IF EXISTS llm_budgets_isolation_policy ON llm_budgets")
    op.execute("DROP POLICY IF EXISTS llm_usage_isolation_policy ON llm_usage")
    
    # Note: RLS remains enabled but locked down (Supabase Best Practice)
