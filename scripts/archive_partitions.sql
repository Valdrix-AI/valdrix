-- archive_partitions.sql
-- Optional DBA bootstrap for the scheduler-owned partition archival path.
--
-- The application now performs partition movement via
-- `app.shared.core.maintenance.PartitionMaintenanceService`. This SQL is kept as
-- a deterministic bootstrap helper for operators who want the archive table and
-- unique index provisioned before the first maintenance sweep.

CREATE TABLE IF NOT EXISTS public.cost_records_archive (
    LIKE public.cost_records INCLUDING ALL
);

ALTER TABLE public.cost_records_archive
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS ux_cost_records_archive_id_recorded_at
    ON public.cost_records_archive (id, recorded_at);

