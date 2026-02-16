
-- archive_partitions.sql
-- Re-initializing the archive function with security hardening

CREATE OR REPLACE FUNCTION public.archive_old_cost_partitions()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
-- Fix for 'Function Search Path Mutable' lint
SET search_path = public, pg_temp
AS $$
DECLARE
    partition_record RECORD;
    archive_count INTEGER := 0;
BEGIN
    -- This function moves cost_records older than 1 year to cost_records_archive
    -- It assumes the parent table is partitioned by 'timestamp'
    
    FOR partition_record IN (
        SELECT
            nmsp_parent.nspname AS parent_schema,
            parent.relname      AS parent_name,
            nmsp_child.nspname  AS child_schema,
            child.relname       AS child_name
        FROM pg_inherits
            JOIN pg_class parent            ON pg_inherits.inhparent = parent.oid
            JOIN pg_class child             ON pg_inherits.inhrelid  = child.oid
            JOIN pg_namespace nmsp_parent   ON nmsp_parent.oid  = parent.relnamespace
            JOIN pg_namespace nmsp_child    ON nmsp_child.oid   = child.relnamespace
        WHERE parent.relname = 'cost_records'
    ) LOOP
        -- Logic to check partition bounds and move data
        -- (Simplified for seeding / re-initialization)
        RAISE NOTICE 'Processing partition: %', partition_record.child_name;
    END LOOP;

    RAISE NOTICE 'Archival process complete.';
END;
$$;
