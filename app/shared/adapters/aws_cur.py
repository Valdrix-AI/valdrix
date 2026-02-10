"""
AWS Cost and Usage Report (CUR) Ingestion Service

Ingests granular, high-fidelity Parquet files from S3 to provide 
tag-based attribution and source-of-truth cost data.
"""

import os
import json
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List
import aioboto3
import pandas as pd
import pyarrow.parquet as pq
import structlog
from app.shared.adapters.base import CostAdapter
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

    async def verify_connection(self) -> bool:
        """Verify S3 access."""
        try:
            creds = await self._get_credentials()
            async with self.session.client(
                "s3",
                region_name=self.connection.region,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            ) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error("cur_bucket_verify_failed", bucket=self.bucket_name, error=str(e))
            return False

    async def setup_cur_automation(self) -> Dict[str, Any]:
        """
        Automates the creation of an S3 bucket and CUR report definition.
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
                # 1. Check if bucket exists
                from botocore.exceptions import ClientError
                bucket_exists = True
                try:
                    await s3.head_bucket(Bucket=self.bucket_name)
                except ClientError as e:
                    if e.response["Error"]["Code"] in ["404", "403"]:
                        bucket_exists = False
                    else:
                        raise

                # 2. Create bucket if needed
                if not bucket_exists:
                    if self.connection.region == "us-east-1":
                        await s3.create_bucket(Bucket=self.bucket_name)
                    else:
                        await s3.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.connection.region}
                        )

                # 3. Put bucket policy
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "AllowCURPutObject",
                            "Effect": "Allow",
                            "Principal": {"Service": "billingreports.amazonaws.com"},
                            "Action": "s3:PutObject",
                            "Resource": f"arn:aws:s3:::{self.bucket_name}/*",
                            "Condition": {
                                "StringEquals": {
                                    "aws:SourceAccount": self.connection.aws_account_id,
                                    "aws:SourceArn": f"arn:aws:cur:us-east-1:{self.connection.aws_account_id}:definition/*"
                                }
                            }
                        },
                        {
                            "Sid": "AllowCURGetBucketAcl",
                            "Effect": "Allow",
                            "Principal": {"Service": "billingreports.amazonaws.com"},
                            "Action": "s3:GetBucketAcl",
                            "Resource": f"arn:aws:s3:::{self.bucket_name}"
                        }
                    ]
                }
                await s3.put_bucket_policy(Bucket=self.bucket_name, Policy=json.dumps(policy))

            except Exception as e:
                logger.error("s3_setup_failed", error=str(e))
                return {"status": "error", "message": f"S3 setup failed: {str(e)}"}

        async with self.session.client(
            "cur",
            region_name="us-east-1", # CUR is global but uses us-east-1 endpoint
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as cur:
            try:
                # 4. Create CUR Report Definition
                report_name = f"valdrix-cur-{self.connection.aws_account_id}"
                await cur.put_report_definition(
                    ReportDefinition={
                        'ReportName': report_name,
                        'TimeUnit': 'HOURLY',
                        'Format': 'Parquet',
                        'Compression': 'GZIP',
                        'AdditionalSchemaElements': ['RESOURCES'],
                        'S3Bucket': self.bucket_name,
                        'S3Prefix': 'cur',
                        'S3Region': self.connection.region,
                        'ReportVersioning': 'OVERWRITE_REPORT',
                        'RefreshClosedReports': True
                    }
                )
                
                return {
                    "status": "success",
                    "bucket_name": self.bucket_name,
                    "report_name": report_name
                }
            except Exception as e:
                logger.error("cur_setup_failed", error=str(e))
                return {"status": "error", "message": f"CUR setup failed: {str(e)}"}

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Normalized cost interface."""
        summary = await self.ingest_latest_parquet()
        return [r.dict() for r in summary.records]

    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """
        CUR adapters do not typically discover live resources; they process
        historical billing records. Use AWSAdapter for live discovery.
        """
        return []

    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        """
        Stream cost data from CUR Parquet files.
        """
        summary = await self.ingest_latest_parquet()
        for record in summary.records:
            # Normalize to dict format expected by stream consumers
            yield {
                "timestamp": record.date,
                "service": record.service,
                "region": record.region,
                "cost_usd": record.amount,
                "currency": record.currency,
                "amount_raw": record.amount_raw,
                "usage_type": record.usage_type,
                "tags": record.tags
            }

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
                paginator = s3.get_paginator("list_objects_v2")
                parquet_objects: List[Dict[str, Any]] = []
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix="cur/"):
                    for obj in page.get("Contents", []):
                        key = obj.get("Key", "")
                        if key.lower().endswith(".parquet"):
                            parquet_objects.append(obj)

                if not parquet_objects:
                    logger.warning("no_cur_files_found", bucket=self.bucket_name)
                    return self._empty_summary()

                # Sort by last modified
                files = sorted(parquet_objects, key=lambda x: x.get("LastModified") or datetime.min, reverse=True)
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

        # AWS CUR Column Aliases
        CUR_COLUMNS = {
            "date": ["lineItem/UsageStartDate", "identity/TimeInterval", "line_item_usage_start_date"],
            "cost": ["lineItem/UnblendedCost", "line_item_unblended_cost"],
            "currency": ["lineItem/CurrencyCode", "line_item_currency_code"],
            "service": ["lineItem/ProductCode", "line_item_product_code", "product/ProductName"],
            "region": ["product/region", "lineItem/AvailabilityZone"],
            "usage_type": ["lineItem/UsageType"]
        }

        # Iterate through row groups
        parse_errors = 0
        for i in range(parquet_file.num_row_groups):
            try:
                table = parquet_file.read_row_group(i)
                df_chunk = table.to_pandas()
            except Exception as e:
                logger.warning("cur_row_group_read_failed", error=str(e), row_group=i)
                continue

            if df_chunk.empty:
                continue
            
            # Resolve columns for this chunk
            col_map = {k: next((c for c in v if c in df_chunk.columns), None) for k, v in CUR_COLUMNS.items()}
            missing = [key for key in ("date", "cost") if not col_map.get(key)]
            if missing:
                logger.warning("cur_missing_required_columns", missing=missing, row_group=i)
                continue

            # Update date range
            chunk_min = pd.to_datetime(df_chunk[col_map["date"]].min()).date()
            chunk_max = pd.to_datetime(df_chunk[col_map["date"]].max()).date()
            min_date = min(min_date, chunk_min) if min_date else chunk_min
            max_date = max(max_date, chunk_max) if max_date else chunk_max

            # Process rows in chunk
            for _, row in df_chunk.iterrows():
                try:
                    record = self._parse_row(row, col_map)
                except Exception as e:
                    parse_errors += 1
                    if parse_errors <= 3:
                        logger.warning("cur_row_parse_failed", error=str(e))
                    continue
                
                # Safety valve: For massive files, we limit the records list to prevent OOM
                if len(all_records) < 100000:
                    all_records.append(record)

                # Aggregation
                total_cost_usd += record.amount
                by_service[record.service] = by_service.get(record.service, Decimal("0")) + record.amount
                by_region[record.region] = by_region.get(record.region, Decimal("0")) + record.amount
                
                for tk, tv in record.tags.items():
                    if tk not in by_tag:
                        by_tag[tk] = {}
                    by_tag[tk][tv] = by_tag[tk].get(tv, Decimal("0")) + record.amount

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

    def _parse_row(self, row: pd.Series, col_map: Dict[str, str]) -> CostRecord:
        """Parses a single CUR row into a CostRecord."""
        cost_key = col_map.get("cost")
        raw_value = row.get(cost_key, 0) if cost_key else 0
        if pd.isna(raw_value) or raw_value == "":
            raw_amount = Decimal("0")
        else:
            try:
                raw_amount = Decimal(str(raw_value))
            except (InvalidOperation, ValueError, TypeError):
                raw_amount = Decimal("0")
        if raw_amount.is_nan() or raw_amount.is_infinite():
            raw_amount = Decimal("0")

        currency_key = col_map.get("currency")
        currency_val = row.get(currency_key, "USD") if currency_key else "USD"
        currency = "USD" if pd.isna(currency_val) or currency_val == "" else str(currency_val)

        service_key = col_map.get("service")
        service_val = row.get(service_key, "Unknown") if service_key else "Unknown"
        service = "Unknown" if pd.isna(service_val) or service_val == "" else str(service_val)

        region_key = col_map.get("region")
        region_val = row.get(region_key, "Global") if region_key else "Global"
        region = "Global" if pd.isna(region_val) or region_val == "" else str(region_val)

        usage_key = col_map.get("usage_type")
        usage_val = row.get(usage_key, "Unknown") if usage_key else "Unknown"
        usage_type = "Unknown" if pd.isna(usage_val) or usage_val == "" else str(usage_val)

        tags = self._extract_tags(row)

        # Use raw datetime to preserve hourly granularity
        dt = pd.to_datetime(row[col_map["date"]])
        if pd.isna(dt):
            raise ValueError("Invalid usage start date")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return CostRecord(
            date=dt,
            amount=raw_amount,
            amount_raw=raw_amount,
            currency=currency,
            service=service,
            region=region,
            usage_type=usage_type,
            tags=tags
        )

    def _extract_tags(self, row: pd.Series) -> Dict[str, str]:
        """Extracts user-defined tags from CUR columns."""
        tags = {}
        for k, v in row.items():
            if pd.notna(v) and v != "":
                str_k = str(k)
                if "resourceTags/user:" in str_k:
                    tags[str_k.split("resourceTags/user:")[-1]] = str(v)
                elif "resource_tags_user_" in str_k:
                    tags[str_k.replace("resource_tags_user_", "")] = str(v)
        return tags

    async def _get_credentials(self) -> Dict:
        """Helper to get credentials from existing adapter logic or shared util."""
        # For simplicity, we assume the credentials logic is shared or we re-implement
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
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


    async def get_resource_usage(self, service_name: str, resource_id: str = None) -> List[Dict[str, Any]]:
        """
        Detailed usage metrics are parsed from the CUR records during ingestion.
        """
        return []
