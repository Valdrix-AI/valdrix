import structlog
import re
from datetime import date
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
PARTITION_MAINTENANCE_RECOVERABLE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    SQLAlchemyError,
)
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARTITION_NAME_PATTERN = re.compile(r"^cost_records_(\d{4})_(\d{2})$")

class PartitionMaintenanceService:
    """
    Service to automate PostgreSQL table partitioning.
    Ensures future partitions are pre-created to avoid ingestion failures.
    """
    
    SUPPORTED_TABLES = {"cost_records", "audit_logs"}
    PARTITION_MAINTENANCE_LOCK_ID = 87234091

    def __init__(self, db: AsyncSession):
        self.db = db

    def _backend_name(self) -> str:
        bind = getattr(self.db, "bind", None)
        if bind is None:
            bind_getter = getattr(self.db, "get_bind", None)
            if callable(bind_getter):
                bind = bind_getter()
        return str(getattr(getattr(bind, "dialect", None), "name", "") or "").strip().lower()

    @staticmethod
    def _partition_is_older_than_cutoff(partition_name: str, *, cutoff_month: date) -> bool:
        match = _PARTITION_NAME_PATTERN.match(str(partition_name or "").strip())
        if not match:
            return False
        year = int(match.group(1))
        month = int(match.group(2))
        return date(year, month, 1) < date(cutoff_month.year, cutoff_month.month, 1)

    @staticmethod
    def _validate_identifier(identifier: str) -> str:
        candidate = str(identifier or "").strip()
        if not _SAFE_IDENTIFIER_PATTERN.fullmatch(candidate):
            raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
        return candidate

    async def _fetch_table_columns(self, table_name: str) -> dict[str, str]:
        safe_table_name = self._validate_identifier(table_name)
        result = await self.db.execute(
            text(
                """
                SELECT
                    a.attname AS column_name,
                    pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type
                FROM pg_attribute AS a
                JOIN pg_class AS c ON c.oid = a.attrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.relname = :table_name
                  AND n.nspname = current_schema()
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
                """
            ),
            {"table_name": safe_table_name},
        )
        return {
            str(row.column_name): str(row.column_type)
            for row in result
            if getattr(row, "column_name", None) and getattr(row, "column_type", None)
        }

    async def _ensure_cost_archive_table(self) -> list[str]:
        await self.db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS cost_records_archive (
                    LIKE cost_records INCLUDING ALL
                )
                """
            )
        )
        await self.db.execute(
            text(
                """
                ALTER TABLE cost_records_archive
                ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                """
            )
        )

        source_columns = await self._fetch_table_columns("cost_records")
        archive_columns = await self._fetch_table_columns("cost_records_archive")

        for column_name, column_type in source_columns.items():
            if column_name in archive_columns:
                continue
            safe_column_name = self._validate_identifier(column_name)
            await self.db.execute(
                text(
                    f"ALTER TABLE cost_records_archive "
                    f"ADD COLUMN IF NOT EXISTS {safe_column_name} {column_type}"
                )
            )

        archive_columns = await self._fetch_table_columns("cost_records_archive")
        shared_columns = [
            column_name
            for column_name in source_columns.keys()
            if column_name in archive_columns and column_name != "archived_at"
        ]
        return shared_columns

    async def _list_cost_record_partitions(self) -> list[str]:
        result = await self.db.execute(
            text(
                """
                SELECT child.relname AS partition_name
                FROM pg_inherits
                JOIN pg_class AS parent ON pg_inherits.inhparent = parent.oid
                JOIN pg_class AS child ON pg_inherits.inhrelid = child.oid
                JOIN pg_namespace AS ns ON child.relnamespace = ns.oid
                WHERE parent.relname = 'cost_records'
                  AND ns.nspname = current_schema()
                ORDER BY child.relname
                """
            )
        )
        return [
            str(row.partition_name)
            for row in result
            if getattr(row, "partition_name", None)
        ]

    async def _archive_partition(self, partition_name: str, *, shared_columns: list[str]) -> int:
        safe_partition_name = self._validate_identifier(partition_name)
        if not shared_columns:
            return 0

        source_row_count = int(
            await self.db.scalar(text(f"SELECT COUNT(*) FROM {safe_partition_name}")) or 0
        )
        update_columns = [
            column_name
            for column_name in shared_columns
            if column_name not in {"id", "recorded_at"}
        ]
        column_sql = ", ".join(
            self._validate_identifier(column_name) for column_name in shared_columns
        )
        update_sql = ", ".join(
            f"{self._validate_identifier(column_name)} = EXCLUDED.{self._validate_identifier(column_name)}"
            for column_name in update_columns
        )
        upsert_clause = (
            f"DO UPDATE SET {update_sql}, archived_at = NOW()"
            if update_sql
            else "DO UPDATE SET archived_at = NOW()"
        )
        await self.db.execute(
            text(
                f"""
                INSERT INTO cost_records_archive ({column_sql}, archived_at)
                SELECT {column_sql}, NOW()
                FROM {safe_partition_name}
                ON CONFLICT (id, recorded_at) {upsert_clause}
                """
            )
        )
        await self.db.execute(text(f"DELETE FROM {safe_partition_name}"))
        await self.db.execute(text(f"DROP TABLE IF EXISTS {safe_partition_name}"))
        logger.info(
            "partition_archived",
            partition=safe_partition_name,
            archived_rows=source_row_count,
        )
        return source_row_count

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
                    except PARTITION_MAINTENANCE_RECOVERABLE_EXCEPTIONS as e:
                        logger.error("partition_creation_failed", table=table, partition=partition_name, error=str(e))
                        
        return created_count

    async def archive_old_partitions(self, months_old: int = 13) -> int:
        """
        Move old cost-record partitions into archive storage and retire the partition.
        """
        try:
            if self._backend_name() and self._backend_name() != "postgresql":
                logger.info(
                    "partition_archival_skipped_unsupported_backend",
                    backend=self._backend_name(),
                )
                return 0

            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": self.PARTITION_MAINTENANCE_LOCK_ID},
            )
            shared_columns = await self._ensure_cost_archive_table()
            cutoff_month = date.today() - relativedelta(months=months_old)
            partitions = await self._list_cost_record_partitions()

            archived_rows = 0
            for partition_name in partitions:
                if not self._partition_is_older_than_cutoff(
                    partition_name, cutoff_month=cutoff_month
                ):
                    continue
                archived_rows += await self._archive_partition(
                    partition_name, shared_columns=shared_columns
                )

            return archived_rows
        except PARTITION_MAINTENANCE_RECOVERABLE_EXCEPTIONS as e:
            logger.warning("partition_archival_failed", error=str(e))
            return 0
