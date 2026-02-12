import structlog
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.shared.db.session import async_session_maker

logger = structlog.get_logger()

class CURIngestionJob:
    """
    Background job to ingest AWS CUR data from S3.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def run(self, connection_id: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
        """
        Execute ingestion for a specific connection or all CUR-enabled connections.
        """
        # If no session provided, use the global maker (for standalone job runs)
        if not self.db:
            async with async_session_maker() as session:
                self.db = session
                await self._execute(connection_id, tenant_id)
        else:
            await self._execute(connection_id, tenant_id)

    async def _execute(
        self,
        connection_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        db_session = db or self.db
        if db_session is None:
            raise RuntimeError("Database session is required for CUR ingestion")

        # 1. Fetch connection(s)
        if not tenant_id:
            raise ValueError("tenant_id is required for CUR ingestion scope")

        query = select(AWSConnection)
        if connection_id:
            query = query.where(AWSConnection.id == connection_id)
        query = query.where(AWSConnection.tenant_id == tenant_id)
        
        # We only want connections where CUR is configured (e.g. has bucket info)
        # Note: CUR configuration status might be stored in metadata or a flag
        result = await db_session.execute(query)
        connections = result.scalars().all()

        for conn in connections:
            try:
                await self.ingest_for_connection(conn)
            except Exception as e:
                logger.error("cur_ingestion_connection_failed", connection_id=str(conn.id), error=str(e))

    async def ingest_for_connection(self, connection: AWSConnection) -> None:
        """
        Ingest the latest CUR data for a connection.
        """
        # 1. Discover latest files (simplified for now: looking in standard bucket)
        # In production, we'd read the manifest file.
        bucket = connection.cur_bucket_name or f"valdrix-cur-{connection.aws_account_id}-{connection.region}"
        
        # For demonstration, we assume a path. Real discovery would use s3.list_objects_v2
        # logger.info("cur_ingestion_started", account=connection.aws_account_id, bucket=bucket)
        
        # Example discovery logic (pseudo)
        # latest_key = await self._find_latest_cur_key(connection, bucket)
        # data = await adapter.fetch_cur_data(latest_key)
        # records = adapter.process_dataframe(data)
        
        # 2. Bulk Insert into partitioned table
        # We use 'ON CONFLICT DO NOTHING' or UPSERT logic to handle idempotency
        # Since we use id as PK (UUID) and recorded_at as partition key, 
        # but CUR records don't have our UUID. We'd map them by (account, timestamp, usage_type, etc.)
        
        logger.info("cur_ingestion_simulated_success", connection_id=str(connection.id), bucket=bucket)

    async def _find_latest_cur_key(self, connection: AWSConnection, bucket: str) -> str:
        # Implementation of S3 listing and manifest parsing
        raise NotImplementedError("CUR key discovery is not yet implemented")
