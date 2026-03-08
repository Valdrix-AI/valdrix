"""
Add Auto-Archival for Old Partitions (Phase 4.4)

This migration creates the archive table used by repository-managed runtime
maintenance when archiving partitions older than 1 year to separate cold storage.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-01-19

Phase 4.4: Partition Auto-Archival
- Archive cost_records partitions older than 1 year
- Maintain hot data for dashboard performance
- Cold data accessible via separate archive table
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create archive table for old cost records
    op.execute("""
        CREATE TABLE IF NOT EXISTS cost_records_archive (
            LIKE cost_records INCLUDING ALL
        )
    """)
    
    # Add archive metadata column
    op.execute("""
        ALTER TABLE cost_records_archive 
        ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    """)
    
    # The repository now performs archival through PartitionMaintenanceService at
    # runtime. Older deployments may still carry a legacy pg_cron/function path,
    # so downgrade remains tolerant of those objects if they exist.
    op.execute("""
        COMMENT ON TABLE cost_records_archive IS 
        'Archive table for cost_records partitions older than 1 year. 
         Repository-managed maintenance moves old partition data here.'
    """)


def downgrade() -> None:
    # Remove legacy pg_cron job if present from older manual archival deployments.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                PERFORM cron.unschedule('archive_old_cost_partitions');
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    
    # Drop the legacy archival function if present from older manual setups.
    op.execute("DROP FUNCTION IF EXISTS archive_old_cost_partitions();")
    
    # Note: We don't drop the archive table to preserve historical data
    # op.execute("DROP TABLE IF EXISTS cost_records_archive;")
