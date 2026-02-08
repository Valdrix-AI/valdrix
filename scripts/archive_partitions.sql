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
        -- Parse pg_get_expr(relpartbound) to extract the upper partition bound
        -- Format is usually: FOR VALUES FROM ('YYYY-MM-DD') TO ('YYYY-MM-DD')
        DECLARE
            upper_bound_str TEXT;
            part_end_date DATE;
        BEGIN
            upper_bound_str := substring(partition_record.partition_expr from 'TO \(''(.*)''\)');
            IF upper_bound_str IS NOT NULL THEN
                part_end_date := upper_bound_str::DATE;
                
                IF part_end_date <= cutoff_date THEN
                    RAISE NOTICE 'Archiving partition % (Upper Bound: %)', 
                        partition_record.child_table, part_end_date;
                    
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
            END IF;
        END;
    END LOOP;

    RAISE NOTICE 'Finished archival. % partitions moved to cost_records_archive', archive_count;
END;
$$ LANGUAGE plpgsql;
