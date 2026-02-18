import structlog
from datetime import date
from dateutil.relativedelta import relativedelta  # type: ignore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

class PartitionMaintenanceService:
    """
    Service to automate PostgreSQL table partitioning.
    Ensures future partitions are pre-created to avoid ingestion failures.
    """
    
    SUPPORTED_TABLES = {"cost_records", "audit_logs"}
    PARTITION_MAINTENANCE_LOCK_ID = 87234091

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_future_partitions(self, months_ahead: int = 3) -> int:
        """
        Pre-creates partitions for all supported tables.
        Returns the count of new partitions created.
        """
        today = date.today()
        created_count = 0
        
        # Acquire advisory lock to prevent concurrent maintenance
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": self.PARTITION_MAINTENANCE_LOCK_ID},
        )

        for table in self.SUPPORTED_TABLES:
            prefix = "p" if table == "audit_logs" else ""
            
            for i in range(months_ahead + 1):
                target_date = today + relativedelta(months=i)
                year, month = target_date.year, target_date.month
                partition_name = f"{table}_{prefix}{year}_{month:02d}"
                
                # Check existance
                exists = await self.db.scalar(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_tables 
                            WHERE tablename = :name 
                            AND schemaname = current_schema()
                        )
                    """),
                    {"name": partition_name}
                )
                
                if not exists:
                    start_str = date(year, month, 1).isoformat()
                    end_str = (date(year, month, 1) + relativedelta(months=1)).isoformat()
                    
                    try:
                        await self.db.execute(text(f"""
                            CREATE TABLE IF NOT EXISTS {partition_name} 
                            PARTITION OF {table} 
                            FOR VALUES FROM ('{start_str}') TO ('{end_str}')
                        """))
                        # For production-grade multi-tenant safety, always enable RLS
                        # even if the parent has it, for consistency and defense-in-depth.
                        await self.db.execute(text(f"ALTER TABLE {partition_name} ENABLE ROW LEVEL SECURITY"))
                        await self.db.execute(text(f"ALTER TABLE {partition_name} FORCE ROW LEVEL SECURITY"))
                        
                        created_count += 1
                        logger.info("partition_created", table=table, partition=partition_name)
                    except Exception as e:
                        logger.error("partition_creation_failed", table=table, partition=partition_name, error=str(e))
                        
        return created_count

    async def archive_old_partitions(self, months_old: int = 13) -> int:
        """
        Moves partitions older than N months to the archive table.
        Note: This is a placeholder for the logic in archive_partitions.sql
        """
        # For now, we delegate to the existing PL/pgSQL function if it exists
        try:
            await self.db.execute(text("SELECT archive_old_cost_partitions();"))
            return 1 # Simplified return
        except Exception as e:
            logger.warning("archival_function_call_failed", error=str(e))
            return 0
