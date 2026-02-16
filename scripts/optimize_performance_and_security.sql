-- performance_and_security_hardening.sql
-- Optimizes RLS lookups and adds missing indices for foreign keys.

BEGIN;

-- ==========================================
-- 1. RLS PERFORMANCE OPTIMIZATION (initplan)
-- ==========================================

-- Wrap current_setting() in (SELECT ...) to prevent re-evaluation per row.

-- Tenants
DROP POLICY IF EXISTS tenant_isolation_policy ON tenants;
CREATE POLICY tenant_isolation_policy ON tenants
USING (id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- General Tenant-Scoped Tables
DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'aws_connections', 'carbon_settings', 'cloud_accounts', 'cost_records',
        'llm_budgets', 'llm_usage', 'notification_settings', 'remediation_requests',
        'remediation_settings', 'users', 'anomaly_markers', 'tenant_identity_settings',
        'saas_connections', 'license_connections', 'platform_connections',
        'hybrid_connections', 'scim_groups', 'scim_group_members', 'audit_logs'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_isolation_policy ON %I', t, t);
        EXECUTE format('CREATE POLICY %I_isolation_policy ON %I USING (tenant_id = (SELECT current_setting(''app.current_tenant_id'', TRUE))::uuid)', t, t);
    END LOOP;
END $$;

-- Background Jobs
DROP POLICY IF EXISTS background_jobs_isolation_policy ON background_jobs;
DROP POLICY IF EXISTS background_jobs_tenant_isolation ON background_jobs;
CREATE POLICY background_jobs_isolation_policy ON background_jobs
USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- Provider Invoices
DROP POLICY IF EXISTS tenant_isolation_provider_invoices ON provider_invoices;
CREATE POLICY tenant_isolation_provider_invoices ON provider_invoices
USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- ==========================================
-- 2. FOREIGN KEY INDEXING (Performance)
-- ==========================================

-- Standardize on ix_ prefix for consistency with migrations.
-- Drop old idx_ prefixed indexes if they exist to reduce noise.

-- Audit Logs
DROP INDEX IF EXISTS idx_audit_logs_actor_id;
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id ON audit_logs (actor_id);

-- Carbon
DROP INDEX IF EXISTS idx_carbon_factor_sets_created_by;
DROP INDEX IF EXISTS ix_carbon_factor_sets_created_by;
CREATE INDEX IF NOT EXISTS ix_carbon_factor_sets_created_by_user_id ON carbon_factor_sets (created_by_user_id);

DROP INDEX IF EXISTS idx_carbon_factor_update_logs_actor;
DROP INDEX IF EXISTS ix_carbon_factor_update_logs_actor;
CREATE INDEX IF NOT EXISTS ix_carbon_factor_update_logs_actor_user_id ON carbon_factor_update_logs (actor_user_id);

-- Accounts
DROP INDEX IF EXISTS idx_cloud_accounts_tenant_id;
CREATE INDEX IF NOT EXISTS ix_cloud_accounts_tenant_id ON cloud_accounts (tenant_id);

-- Cost Allocations (Composite)
DROP INDEX IF EXISTS idx_cost_allocations_rule_id;
CREATE INDEX IF NOT EXISTS ix_cost_allocations_rule_id ON cost_allocations (rule_id);
DROP INDEX IF EXISTS idx_cost_allocations_composite_record;
CREATE INDEX IF NOT EXISTS ix_cost_allocations_composite_record ON cost_allocations (cost_record_id, recorded_at);

-- Cost Audit Logs (Composite)
DROP INDEX IF EXISTS idx_cost_audit_logs_composite_record;
DROP INDEX IF EXISTS ix_cost_audit_logs_composite_record;
CREATE INDEX IF NOT EXISTS ix_cost_audit_logs_composite_record ON cost_audit_logs (cost_record_id, cost_recorded_at);

-- Remediation
DROP INDEX IF EXISTS idx_remediation_requests_requested_by;
DROP INDEX IF EXISTS ix_remediation_requests_requested_by;
CREATE INDEX IF NOT EXISTS ix_remediation_requests_requested_by_user_id ON remediation_requests (requested_by_user_id);

DROP INDEX IF EXISTS idx_remediation_requests_reviewed_by;
DROP INDEX IF EXISTS ix_remediation_requests_reviewed_by;
CREATE INDEX IF NOT EXISTS ix_remediation_requests_reviewed_by_user_id ON remediation_requests (reviewed_by_user_id);

-- Strategy
DROP INDEX IF EXISTS idx_strategy_recommendations_strategy_id;
CREATE INDEX IF NOT EXISTS ix_strategy_recommendations_strategy_id ON strategy_recommendations (strategy_id);

-- ==========================================
-- 3. MATERIALIZED VIEW INDEXING (Consistency)
-- ==========================================

-- Standardize Materialized View indexes to ix_
DROP INDEX IF EXISTS idx_mv_daily_cost_tenant_date;
DROP INDEX IF EXISTS ix_mv_daily_cost_tenant_date;
CREATE INDEX IF NOT EXISTS ix_mv_daily_cost_tenant_date ON mv_daily_cost_aggregates (tenant_id, cost_date);

DROP INDEX IF EXISTS idx_mv_daily_cost_unique;
DROP INDEX IF EXISTS ix_mv_daily_cost_unique;
CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_daily_cost_unique ON mv_daily_cost_aggregates (tenant_id, service, region, cost_date);

COMMIT;
