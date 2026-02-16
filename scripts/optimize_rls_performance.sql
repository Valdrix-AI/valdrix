-- RLS Performance Optimization Script
-- Wraps current_setting() lookups in (SELECT ...) subqueries to prevent re-evaluation for each row.
-- This satisfies the Supabase linter (auth_rls_initplan).

BEGIN;

-- 1. Tenants
DROP POLICY IF EXISTS tenant_isolation_policy ON tenants;
CREATE POLICY tenant_isolation_policy ON tenants
USING (id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- 2. General Tenant-Scoped Tables
DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'aws_connections',
        'carbon_settings',
        'cloud_accounts',
        'cost_records',
        'llm_budgets',
        'llm_usage',
        'notification_settings',
        'remediation_requests',
        'remediation_settings',
        'users',
        'anomaly_markers',
        'tenant_identity_settings',
        'saas_connections',
        'license_connections',
        'platform_connections',
        'hybrid_connections',
        'scim_groups',
        'scim_group_members',
        'audit_logs'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_isolation_policy ON %I', t, t);
        EXECUTE format('CREATE POLICY %I_isolation_policy ON %I USING (tenant_id = (SELECT current_setting(''app.current_tenant_id'', TRUE))::uuid)', t, t);
    END LOOP;
END $$;

-- 3. Special Case Policy Names
-- Background Jobs
DROP POLICY IF EXISTS background_jobs_isolation_policy ON background_jobs;
DROP POLICY IF EXISTS background_jobs_tenant_isolation ON background_jobs;
CREATE POLICY background_jobs_isolation_policy ON background_jobs
USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- Provider Invoices
DROP POLICY IF EXISTS tenant_isolation_provider_invoices ON provider_invoices;
CREATE POLICY tenant_isolation_provider_invoices ON provider_invoices
USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);

-- Tenant Subscriptions (if exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'tenant_subscriptions') THEN
        DROP POLICY IF EXISTS tenant_subscriptions_isolation_policy ON tenant_subscriptions;
        CREATE POLICY tenant_subscriptions_isolation_policy ON tenant_subscriptions
        USING (tenant_id = (SELECT current_setting('app.current_tenant_id', TRUE))::uuid);
    END IF;
END $$;

COMMIT;
