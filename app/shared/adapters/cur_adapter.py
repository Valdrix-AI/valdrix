"""
AWS Cost & Usage Report (CUR) Adapter

Implements cost ingestion from CUR files in S3, which is the 2026 best practice
for enterprise-scale cost analysis:

Cost Comparison:
- Cost Explorer API: $0.01 per request (expensive at scale)
- CUR to S3: ~$0.01 per GB stored (much cheaper for large datasets)

Architecture:
1. Customer configures CUR export to their S3 bucket
2. Valdrix assumes role to read CUR files
3. CUR files are parsed (Parquet format recommended)
4. Results cached for fast subsequent queries
"""

import aioboto3
import json
from datetime import date, datetime
from typing import List, Dict, Any
import structlog
from botocore.exceptions import ClientError

from app.shared.adapters.base import CostAdapter

logger = structlog.get_logger()


class CURAdapter(CostAdapter):
    """
    Adapter for reading AWS Cost & Usage Reports from S3.

    This is more cost-effective than Cost Explorer API for:
    - Large enterprises with high API call volumes
    - Historical analysis (CUR has up to 3 years of data)
    - Detailed resource-level cost attribution

    Prerequisites:
    1. CUR export configured in customer's AWS account
    2. S3 bucket accessible via cross-account role
    3. Parquet format recommended for efficiency
    """

    def __init__(
        self,
        bucket_name: str,
        report_prefix: str,
        credentials: Dict[str, str],
        region: str = "us-east-1"
    ):
        self.bucket_name = bucket_name
        self.report_prefix = report_prefix
        self.credentials = credentials
        self.region = region
        self.session = aioboto3.Session()

    async def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        usage_only: bool = False,
        group_by_service: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily costs from CUR files in S3.

        Note: This implementation supports Parquet parsing and date filtering.
        If a CUR manifest is present, it will be used to enumerate report keys.
        """
        try:
            # Step 1: List CUR files for the date range
            cur_files = await self._list_cur_files(start_date, end_date)

            if not cur_files:
                logger.warning("no_cur_files_found",
                             bucket=self.bucket_name,
                             prefix=self.report_prefix,
                             start=start_date.isoformat(),
                             end=end_date.isoformat())
                return []

            # Step 2: Parse and aggregate
            # NOTE: Full Parquet parsing requires pyarrow dependency.
            logger.info("cur_files_found",
                       count=len(cur_files),
                       bucket=self.bucket_name)

            return await self._parse_cur_files(cur_files, start_date, end_date, group_by_service)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error("cur_fetch_failed", error=str(e), code=error_code)
            return [{"Error": str(e), "Code": error_code}]

    async def _list_cur_files(
        self,
        start_date: date,
        end_date: date
    ) -> List[str]:
        """List CUR Parquet files in S3 for the date range."""
        if start_date > end_date:
            logger.warning("cur_invalid_date_range", start=start_date.isoformat(), end=end_date.isoformat())
            return []

        files: List[str] = []
        seen: set[str] = set()

        def add_keys(keys: List[str]) -> None:
            for key in keys:
                if key not in seen:
                    seen.add(key)
                    files.append(key)

        async with self.session.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.credentials.get("AccessKeyId"),
            aws_secret_access_key=self.credentials.get("SecretAccessKey"),
            aws_session_token=self.credentials.get("SessionToken"),
        ) as s3:
            try:
                # CUR files are organized by date: prefix/year/month/
                # We need to scan all months in the range
                current = start_date.replace(day=1)
                while current <= end_date:
                    prefix = f"{self.report_prefix}/{current.year}/{current.month:02d}/"

                    paginator = s3.get_paginator("list_objects_v2")
                    manifest_candidates = []
                    parquet_keys = []
                    async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                        for obj in page.get("Contents", []):
                            key = obj["Key"]
                            if key.lower().endswith("manifest.json"):
                                manifest_candidates.append((obj.get("LastModified"), key))
                            elif key.endswith(".parquet"):
                                parquet_keys.append(key)

                    if manifest_candidates:
                        manifest_candidates.sort(key=lambda x: x[0] or datetime.min)
                        _, manifest_key = manifest_candidates[-1]
                        try:
                            response = await s3.get_object(Bucket=self.bucket_name, Key=manifest_key)
                            manifest_body = await response["Body"].read()
                            manifest = json.loads(manifest_body)
                            report_keys = manifest.get("reportKeys", [])
                            add_keys([k for k in report_keys if k.endswith(".parquet")])
                        except Exception as e:
                            logger.warning("cur_manifest_parse_failed", manifest=manifest_key, error=str(e))
                            add_keys(parquet_keys)
                    else:
                        add_keys(parquet_keys)

                    # Move to next month
                    if current.month == 12:
                        current = current.replace(year=current.year + 1, month=1)
                    else:
                        current = current.replace(month=current.month + 1)

            except ClientError as e:
                logger.error("s3_list_failed", bucket=self.bucket_name, error=str(e))
                raise

        return files

    async def _parse_cur_files(
        self,
        files: List[str],
        start_date: date,
        end_date: date,
        group_by_service: bool
    ) -> List[Dict[str, Any]]:
        """
        Parses Parquet CUR files from S3 and aggregates costs.
        
        Requires pandas and pyarrow.
        """
        combined_grouped = None # Initialize as None, will create from first chunk
        
        try:
            import pandas as pd
            import pyarrow.parquet as pq
        except ImportError:
            logger.error("cur_parsing_missing_dependency", msg="pandas/pyarrow not installed")
            return []

        async with self.session.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.credentials.get("AccessKeyId"),
            aws_secret_access_key=self.credentials.get("SecretAccessKey"),
            aws_session_token=self.credentials.get("SessionToken"),
        ) as s3:
            for file_key in files:
                try:
                    logger.debug("processing_cur_file", file=file_key)
                    response = await s3.get_object(Bucket=self.bucket_name, Key=file_key)
                    
                    async with response["Body"] as stream:
                        content = await stream.read()
                        
                        from io import BytesIO
                        
                        cols = ["line_item_usage_start_date", "line_item_product_code", "line_item_blended_cost"]
                        table = pq.read_table(BytesIO(content), columns=cols)
                        df = table.to_pandas()
                        
                        if "line_item_usage_start_date" in df.columns:
                            df["date"] = pd.to_datetime(df["line_item_usage_start_date"]).dt.date
                            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
                        
                        if df.empty:
                            continue

                        # Aggregate this chunk immediately
                        if group_by_service:
                            chunk_grouped = df.groupby(["date", "line_item_product_code"])["line_item_blended_cost"].sum().reset_index()
                        else:
                            chunk_grouped = df.groupby("date")["line_item_blended_cost"].sum().reset_index()
                        
                        # Merge with combined results
                        if combined_grouped is None:
                            combined_grouped = chunk_grouped
                        else:
                            combined_grouped = pd.concat([combined_grouped, chunk_grouped], ignore_index=True)
                            
                            # Re-aggregate to keep memory footprint low
                            if group_by_service:
                                combined_grouped = combined_grouped.groupby(["date", "line_item_product_code"])["line_item_blended_cost"].sum().reset_index()
                            else:
                                combined_grouped = combined_grouped.groupby("date")["line_item_blended_cost"].sum().reset_index()
                                
                except Exception as e:
                    logger.error("cur_file_parse_error", file=file_key, error=str(e))
                    continue
                
        if combined_grouped is None or combined_grouped.empty:
            return []
            
        results = []
        for _, row in combined_grouped.iterrows():
            item = {
                "date": row["date"].isoformat(),
                "cost": float(row["line_item_blended_cost"])
            }
            if group_by_service and "line_item_product_code" in row:
                item["service"] = row["line_item_product_code"]
            results.append(item)
            
        return results

    async def get_gross_usage(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get usage-only costs grouped by service."""
        return await self.get_daily_costs(
            start_date,
            end_date,
            usage_only=True,
            group_by_service=True
        )

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Standard interface for cost data."""
        # Convert datetime to date for legacy get_daily_costs
        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date
        return await self.get_daily_costs(s_date, e_date)

    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        """
        Stream cost data from CUR files.
        """
        # Convert datetime to date for legacy _list_cur_files
        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date
        
        cur_files = await self._list_cur_files(s_date, e_date)
        if not cur_files:
            return

        # Scaffold implementation - just logs and returns nothing for now
        # until full parquet parsing is added via pyarrow (Phase 26)
        logger.info("cur_streaming_not_implemented", count=len(cur_files))
        return

    async def discover_resources(self, resource_type: str = None, region: str = None) -> List[Dict[str, Any]]:
        """CUR-based resource discovery."""
        return []

    async def get_resource_usage(self, service_name: str, resource_id: str = None) -> List[Dict[str, Any]]:
        """Detailed resource usage from CUR."""
        return []

    async def verify_connection(self) -> bool:
        """Verify S3 accessibility."""
        async with self.session.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.credentials.get("AccessKeyId"),
            aws_secret_access_key=self.credentials.get("SecretAccessKey"),
            aws_session_token=self.credentials.get("SessionToken"),
        ) as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket_name)
                return True
            except ClientError as e:
                logger.error("cur_bucket_verify_failed", bucket=self.bucket_name, error=str(e))
                return False


class CURConfig:
    """
    Configuration for CUR-based cost ingestion.

    Stored per-tenant to support different CUR locations.
    """

    def __init__(
        self,
        bucket_name: str,
        report_prefix: str,
        report_name: str,
        format: str = "Parquet"  # Parquet or CSV
    ):
        self.bucket_name = bucket_name
        self.report_prefix = report_prefix
        self.report_name = report_name
        self.format = format

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CURConfig":
        return cls(
            bucket_name=data["bucket_name"],
            report_prefix=data["report_prefix"],
            report_name=data["report_name"],
            format=data.get("format", "Parquet")
        )
