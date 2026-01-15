"""
AWS Cost and Usage Report (CUR) Ingestion Service

Ingests granular, high-fidelity Parquet files from S3 to provide 
tag-based attribution and source-of-truth cost data.
"""

import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, List
import aioboto3
import pandas as pd
import pyarrow.parquet as pq
import pytz
import structlog
from app.services.adapters.base import CostAdapter
from app.models.aws_connection import AWSConnection
from app.schemas.costs import CloudUsageSummary, CostRecord

logger = structlog.get_logger()

class AWSCURAdapter(CostAdapter):
    """
    Ingests AWS CUR (Cost and Usage Report) data from S3.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self.session = aioboto3.Session()
        # Use dynamic bucket name from automated setup, fallback to connection-derived if needed
        self.bucket_name = connection.cur_bucket_name or f"valdrix-cur-{connection.aws_account_id}-{connection.region}"

    async def get_costs(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> CloudUsageSummary:
        """Standardized interface for CUR ingestion."""
        # For now, CUR ingestion returns the latest file which usually covers a month.
        # Future: Filter records by start/end date.
        return await self.ingest_latest_parquet()

    async def ingest_latest_parquet(self) -> CloudUsageSummary:
        """
        Discovers and ingests the latest Parquet file from the CUR bucket.
        """
        creds = await self._get_credentials()
        
        async with self.session.client(
            "s3",
            region_name=self.connection.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            try:
                # 1. List objects in the bucket to find the latest Parquet
                response = await s3.list_objects_v2(Bucket=self.bucket_name, Prefix="cur/")
                if "Contents" not in response:
                    logger.warning("no_cur_files_found", bucket=self.bucket_name)
                    return self._empty_summary()

                # Sort by last modified
                files = sorted(response["Contents"], key=lambda x: x["LastModified"], reverse=True)
                latest_file = files[0]["Key"]

                logger.info("ingesting_cur_file", key=latest_file)

                # 3. Stream download to temporary file (avoids OOM for large files)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
                    tmp_path = tmp.name
                    try:
                        obj = await s3.get_object(Bucket=self.bucket_name, Key=latest_file)
                        async with obj["Body"] as stream:
                            while True:
                                chunk = await stream.read(1024 * 1024 * 8) # 8MB chunks
                                if not chunk:
                                    break
                                tmp.write(chunk)
                        
                        # 4. Streamed Ingestion with PyArrow (Chunked Processing)
                        return self._process_parquet_streamingly(tmp_path)
                        
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)

            except Exception as e:
                logger.error("cur_ingestion_failed", error=str(e))
                raise

    def _process_parquet_streamingly(self, file_path: str) -> CloudUsageSummary:
        """
        Processes a Parquet file using row groups to keep memory low.
        Aggregates metrics on the fly.
        """
        parquet_file = pq.ParquetFile(file_path)
        
        # Initialize Summary
        total_cost_usd = Decimal("0")
        by_service = {}
        by_region = {}
        by_tag = {}
        all_records = [] # Still keeping records for now, but could be limited if needed
        
        min_date = None
        max_date = None

        # Standard AWS CUR Columns
        data_map = {
            "date": ["lineItem/UsageStartDate", "identity/TimeInterval", "line_item_usage_start_date"],
            "cost": ["lineItem/UnblendedCost", "line_item_unblended_cost"],
            "currency": ["lineItem/CurrencyCode", "line_item_currency_code"],
            "service": ["lineItem/ProductCode", "line_item_product_code", "product/ProductName"],
            "region": ["product/region", "lineItem/AvailabilityZone"],
            "usage_type": ["lineItem/UsageType"]
        }

        # Iterate through row groups
        for i in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(i)
            df_chunk = table.to_pandas()
            
            # Resolve columns for this chunk
            date_col = next((c for c in data_map["date"] if c in df_chunk.columns), df_chunk.columns[0])
            cost_col = next((c for c in data_map["cost"] if c in df_chunk.columns), "cost")
            curr_col = next((c for c in data_map["currency"] if c in df_chunk.columns), None)
            svc_col = next((c for c in data_map["service"] if c in df_chunk.columns), "service")
            reg_col = next((c for c in data_map["region"] if c in df_chunk.columns), None)
            type_col = next((c for c in data_map["usage_type"] if c in df_chunk.columns), None)

            # Update date range
            chunk_min = pd.to_datetime(df_chunk[date_col].min()).date()
            chunk_max = pd.to_datetime(df_chunk[date_col].max()).date()
            min_date = min(min_date, chunk_min) if min_date else chunk_min
            max_date = max(max_date, chunk_max) if max_date else chunk_max

            # Process rows in chunk
            for _, row in df_chunk.iterrows():
                raw_amount = Decimal(str(row.get(cost_col, 0)))
                currency = str(row.get(curr_col, "USD"))
                amount_usd = raw_amount # Simplified conversion for now
                
                service = str(row.get(svc_col, "Unknown"))
                region = str(row.get(reg_col, "Global"))
                usage_type = str(row.get(type_col, "Unknown"))

                tags = {}
                for k, v in row.items():
                    if pd.notna(v) and v != "":
                        str_k = str(k)
                        if "resourceTags/user:" in str_k:
                            tags[str_k.split("resourceTags/user:")[-1]] = str(v)
                        elif "resource_tags_user_" in str_k:
                            tags[str_k.replace("resource_tags_user_", "")] = str(v)

                # Internal Record
                # Use raw datetime to preserve hourly granularity
                dt = pd.to_datetime(row[date_col])
                if dt.tzinfo is None:
                    dt = pytz.UTC.localize(dt)

                record = CostRecord(
                    date=dt,
                    amount=amount_usd,
                    amount_raw=raw_amount,
                    currency=currency,
                    service=service,
                    region=region,
                    usage_type=usage_type,
                    tags=tags
                )
                
                # Safety valve: For massive files, we limit the records list to prevent OOM
                # but we still aggregate EVERYTHING.
                if len(all_records) < 100000:
                    all_records.append(record)

                # Aggregation
                total_cost_usd += amount_usd
                by_service[service] = by_service.get(service, Decimal("0")) + amount_usd
                by_region[region] = by_region.get(region, Decimal("0")) + amount_usd
                
                for tk, tv in tags.items():
                    if tk not in by_tag: by_tag[tk] = {}
                    by_tag[tk][tv] = by_tag[tk].get(tv, Decimal("0")) + amount_usd

        return CloudUsageSummary(
            tenant_id=str(self.connection.tenant_id),
            provider="aws",
            start_date=min_date or date.today(),
            end_date=max_date or date.today(),
            total_cost=total_cost_usd,
            records=all_records,
            by_service=by_service,
            by_region=by_region,
            by_tag=by_tag
        )

    async def _get_credentials(self) -> Dict:
        """Helper to get credentials from existing adapter logic or shared util."""
        # For simplicity, we assume the credentials logic is shared or we re-implement
        from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
        adapter = MultiTenantAWSAdapter(self.connection)
        return await adapter.get_credentials()

    def _empty_summary(self) -> CloudUsageSummary:
        return CloudUsageSummary(
            tenant_id=str(self.connection.tenant_id),
            provider="aws",
            start_date=date.today(),
            end_date=date.today(),
            total_cost=Decimal("0"),
            records=[],
            by_service={},
            by_region={}
        )

    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """Placeholder - CUR usually doesn't discover live resources, but we could parse from tags."""
        return []

    async def get_resource_usage(self, service_name: str, resource_id: str = None) -> List[Dict[str, Any]]:
        """Placeholder - detailed usage resides within the CUR records."""
        return []
