import structlog
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.shared.adapters.aws_utils import resolve_aws_region_hint
from app.shared.db.session import async_session_maker, mark_session_system_context

logger = structlog.get_logger()


class CURIngestionJob:
    """
    Background job to ingest AWS CUR data from S3.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def run(
        self, connection_id: Optional[str] = None, tenant_id: Optional[str] = None
    ) -> None:
        """
        Execute ingestion for a specific connection or all CUR-enabled connections.
        """
        # If no session provided, use the global maker (for standalone job runs)
        if not self.db:
            async with async_session_maker() as session:
                await mark_session_system_context(session)
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
                logger.error(
                    "cur_ingestion_connection_failed",
                    connection_id=str(conn.id),
                    error=str(e),
                )

    async def ingest_for_connection(self, connection: AWSConnection) -> None:
        """
        Ingest the latest CUR data for a connection.
        """
        resolved_region = resolve_aws_region_hint(connection.region)

        # 1. Discover latest files (simplified for now: looking in standard bucket)
        # In production, we'd read the manifest file.
        bucket = (
            connection.cur_bucket_name
            or f"valdrics-cur-{connection.aws_account_id}-{resolved_region}"
        )

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

        logger.info(
            "cur_ingestion_simulated_success",
            connection_id=str(connection.id),
            bucket=bucket,
        )

    async def _find_latest_cur_key(
        self, connection: AWSConnection, bucket: str
    ) -> Optional[str]:
        """
        Discovers the latest CUR manifest and returns the primary Parquet data key.
        Uses a cost-efficient ListObjectsV2/GetObject pattern.
        """
        import boto3
        from botocore.config import Config
        import json

        # 2026 Standard: Use regional endpoints and non-blocking patterns where possible
        resolved_region = resolve_aws_region_hint(connection.region)
        s3 = boto3.client(
            "s3",
            region_name=resolved_region,
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )

        prefix = connection.cur_prefix or ""
        report_name = connection.cur_report_name or "valdrics-cur"

        try:
            # 1. Look for all manifests matching the report name
            # Pattern: [prefix]/[report_name]/[date-range]/[report_name]-Manifest.json
            response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=f"{prefix}/{report_name}/" if prefix else f"{report_name}/",
            )

            if "Contents" not in response:
                logger.warning("cur_bucket_empty", bucket=bucket)
                return None

            # Find the latest manifest by LastModified
            manifests = [
                obj
                for obj in response["Contents"]
                if obj["Key"].endswith("-Manifest.json")
            ]

            if not manifests:
                logger.warning(
                    "cur_manifest_not_found", bucket=bucket, report=report_name
                )
                return None

            latest_manifest_obj = max(manifests, key=lambda x: x["LastModified"])
            manifest_key = latest_manifest_obj["Key"]

            # 2. Extract Parquet keys from the manifest
            manifest_resp = s3.get_object(Bucket=bucket, Key=manifest_key)
            manifest_data = json.loads(manifest_resp["Body"].read().decode("utf-8"))

            # CUR Parquet manifests list files in 'reportKeys'
            report_keys = manifest_data.get("reportKeys", [])
            if not report_keys:
                logger.warning("cur_manifest_empty_files", manifest=manifest_key)
                return None

            # Return the latest file (usually CUR overwrites or versioning applies)
            # For multi-part, we'd return a list, but simplified here to the newest key.
            from typing import cast
            return cast(Optional[str], report_keys[0])

        except Exception as e:
            logger.error("cur_manifest_discovery_failed", error=str(e), bucket=bucket)
            raise
