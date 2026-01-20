"""
Add Materialized View for Cost Aggregation Caching (Phase 4.3)

This migration creates a materialized view for daily cost aggregates
to provide instant API responses for common dashboard queries.

Revision ID: g1h2i3j4k5l6
Revises: f8g9h0i1j2k3_audit_rls_hardening
Create Date: 2026-01-19

Phase 4.3: Query Caching Layer
- Daily aggregate view by tenant, service, region
- Refreshed nightly via pg_cron or background job
- API hits cache first for 100ms responses
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g1h2i3j4k5l6'
down_revision = 'f8g9h0i1j2k3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create materialized view for daily cost aggregates
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_cost_aggregates AS
        SELECT 
            tenant_id,
            service,
            region,
            DATE(recorded_at) as cost_date,
            SUM(cost_usd) as total_cost,
            COALESCE(SUM(carbon_kg), 0) as total_carbon,
            COUNT(*) as record_count
        FROM cost_records
        GROUP BY tenant_id, service, region, DATE(recorded_at)
        WITH DATA;
    """)


    
    # Create unique index for concurrent refresh
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_cost_unique 
        ON mv_daily_cost_aggregates (tenant_id, service, region, cost_date);
    """)
    
    # Create supporting indexes for common query patterns
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mv_daily_cost_tenant_date 
        ON mv_daily_cost_aggregates (tenant_id, cost_date);
    """)
    
    # Optional: Add pg_cron job for nightly refresh (only on Supabase/pg_cron enabled)
    # This is wrapped in a try-catch as pg_cron may not be available
    op.execute("""
        DO $$
        BEGIN
            -- Check if pg_cron extension is available
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                -- Schedule nightly refresh at 2 AM UTC
                PERFORM cron.schedule(
                    'refresh_cost_aggregates',
                    '0 2 * * *',
                    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_aggregates'
                );
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pg_cron not available, skipping scheduled refresh setup';
        END $$;
    """)


def downgrade() -> None:
    # Remove pg_cron job if exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                PERFORM cron.unschedule('refresh_cost_aggregates');
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pg_cron job removal skipped';
        END $$;
    """)
    
    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_daily_cost_aggregates;")
