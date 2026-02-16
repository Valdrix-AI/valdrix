"""audit_rls_hardening

Revision ID: f8g9h0i1j2k3
Revises: e4f5g6h7i8j9
Create Date: 2026-01-16 10:50:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8g9h0i1j2k3'
down_revision: Union[str, Sequence[str], None] = 'e4f5g6h7i8j9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Implement missing RLS policies for background_jobs and tenant_subscriptions."""
    
    # ENSURE TABLE EXISTS BEFORE ENABLING RLS
    op.execute("""
        CREATE TABLE IF NOT EXISTS background_jobs (
            id UUID PRIMARY KEY,
            job_type VARCHAR(50) NOT NULL,
            tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
            status VARCHAR(20) DEFAULT 'pending',
            payload JSONB,
            result JSONB,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            scheduled_for TIMESTAMP WITH TIME ZONE,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # 1. Background Jobs
    op.execute("ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ 
        BEGIN 
            DROP POLICY IF EXISTS background_jobs_isolation_policy ON background_jobs;
            CREATE POLICY background_jobs_isolation_policy ON background_jobs
            USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
        END $$;
    """)


    # 2. Tenant Subscriptions (Conditional because it might be added/dropped in other branches)
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'tenant_subscriptions') THEN
                DROP POLICY IF EXISTS tenant_subscriptions_isolation_policy ON tenant_subscriptions;
                CREATE POLICY tenant_subscriptions_isolation_policy ON tenant_subscriptions
                USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
            END IF;
        END $$;
    """)

    # 3. Discovered Accounts (For multi-cloud org discovery)
    # Ensure tenant_id exists for RLS
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'discovered_accounts') THEN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='discovered_accounts' AND column_name='tenant_id') THEN
                    ALTER TABLE discovered_accounts ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
                END IF;
                ALTER TABLE discovered_accounts ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS discovered_accounts_isolation_policy ON discovered_accounts;
                CREATE POLICY discovered_accounts_isolation_policy ON discovered_accounts
                USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE)::uuid));
            END IF;
        END $$;
    """)



def downgrade() -> None:
    """Drop RLS policies."""
    op.execute("DROP POLICY IF EXISTS background_jobs_isolation_policy ON background_jobs")
    op.execute("DROP POLICY IF EXISTS tenant_subscriptions_isolation_policy ON tenant_subscriptions")
    op.execute("DROP POLICY IF EXISTS discovered_accounts_isolation_policy ON discovered_accounts")
    
    # Note: We keep RLS enabled but polyless (locked down)
