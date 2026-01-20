-- archive_old_cost_partitions.sql
-- Phase 4.4: Partition Auto-Archival
-- Automatically moves partitions older than 1 year to a cold storage archive table.

CREATE OR REPLACE FUNCTION archive_old_cost_partitions()
RETURNS void AS $$
DECLARE
    partition_record RECORD;
    archive_count INTEGER := 0;
    cutoff_date DATE := CURRENT_DATE - INTERVAL '1 year';
BEGIN
    -- 1. Find partitions of cost_records that are older than the cutoff
    -- We look for child tables of 'cost_records' where the range end is before cutoff
    FOR partition_record IN 
        SELECT 
            nmsp_child.nspname  AS child_schema,
            child.relname       AS child_table,
            pg_get_expr(child.relpartbound, child.oid) as partition_expr
        FROM pg_inherits
            JOIN pg_class parent        ON pg_inherits.inhparent = parent.oid
            JOIN pg_class child         ON pg_inherits.inhrelid = child.oid
            JOIN pg_namespace nmsp_parent ON parent.relnamespace = nmsp_parent.oid
            JOIN pg_namespace nmsp_child  ON child.relnamespace = nmsp_child.oid
        WHERE parent.relname='cost_records' 
          AND nmsp_parent.nspname='public'
    LOOP
        -- Simple check: if partition name contains YYYYMM format and is older than cutoff
        -- For RANGE (recorded_at), we'd ideally parse pg_get_expr but that's complex
        -- Assumption: partition naming convention is cost_records_pYYYY_MM
        IF partition_record.child_table ~ '^cost_records_p[0-9]{4}_[0-9]{2}$' THEN
            DECLARE
                part_year INTEGER := split_part(substring(partition_record.child_table from 15), '_', 1)::integer;
                part_month INTEGER := split_part(substring(partition_record.child_table from 15), '_', 2)::integer;
                part_date DATE := make_date(part_year, part_month, 1);
            BEGIN
                IF part_date < cutoff_date THEN
                    RAISE NOTICE 'Archiving partition % (Date: %)', partition_record.child_table, part_date;
                    
                    -- 2. Copy data to archive table
                    EXECUTE format('INSERT INTO cost_records_archive SELECT *, NOW() FROM %I.%I', 
                        partition_record.child_schema, partition_record.child_table);
                    
                    -- 3. Detach and drop the partition
                    EXECUTE format('ALTER TABLE cost_records DETACH PARTITION %I.%I', 
                        partition_record.child_schema, partition_record.child_table);
                    EXECUTE format('DROP TABLE %I.%I', 
                        partition_record.child_schema, partition_record.child_table);
                        
                    archive_count := archive_count + 1;
                END IF;
            END;
        END IF;
    END LOOP;

    RAISE NOTICE 'Finished archival. % partitions moved to cost_records_archive', archive_count;
END;
$$ LANGUAGE plpgsql;
