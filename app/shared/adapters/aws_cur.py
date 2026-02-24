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
from typing import Any, Dict, List, AsyncGenerator, cast
import aioboto3
import pandas as pd
import pyarrow.parquet as pq
import structlog
from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.aws_utils import resolve_aws_region_hint
from app.shared.core.exceptions import ConfigurationError
from app.shared.core.credentials import AWSCredentials
from app.schemas.costs import CloudUsageSummary, CostRecord

logger = structlog.get_logger()


class AWSCURAdapter(BaseAdapter):
    """
    Ingests AWS CUR (Cost and Usage Report) data from S3.
    """
    _SUMMARY_RECORD_CAP = 50000

    def __init__(self, credentials: AWSCredentials):
        self.credentials = credentials
        self._resolved_region = resolve_aws_region_hint(credentials.region)
        self.session = aioboto3.Session()
        # Use dynamic bucket name from automated setup, fallback to connection-derived if needed
        self.bucket_name = (
            credentials.cur_bucket_name
            or f"valdrix-cur-{credentials.account_id}-{self._resolved_region}"
        )

    async def verify_connection(self) -> bool:
        """Verify S3 access."""
        try:
            creds = await self._get_credentials()
            async with self.session.client(
                "s3",
                region_name=self._resolved_region,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            ) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error(
                "cur_bucket_verify_failed", bucket=self.bucket_name, error=str(e)
            )
            return False

    async def setup_cur_automation(self) -> Dict[str, Any]:
        """
        Automates the creation of an S3 bucket and CUR report definition.
        """
        creds = await self._get_credentials()

        async with self.session.client(
            "s3",
            region_name=self._resolved_region,
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
                    if self._resolved_region == "us-east-1":
                        await s3.create_bucket(Bucket=self.bucket_name)
                    else:
                        await s3.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={
                                "LocationConstraint": self._resolved_region
                            },
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
                                    "aws:SourceAccount": self.credentials.account_id,
                                    "aws:SourceArn": f"arn:aws:cur:us-east-1:{self.credentials.account_id}:definition/*",
                                }
                            },
                        },
                        {
                            "Sid": "AllowCURGetBucketAcl",
                            "Effect": "Allow",
                            "Principal": {"Service": "billingreports.amazonaws.com"},
                            "Action": "s3:GetBucketAcl",
                            "Resource": f"arn:aws:s3:::{self.bucket_name}",
                        },
                    ],
                }
                await s3.put_bucket_policy(
                    Bucket=self.bucket_name, Policy=json.dumps(policy)
                )

            except Exception as e:
                logger.error("s3_setup_failed", error=str(e))
                return {"status": "error", "message": f"S3 setup failed: {str(e)}"}

        async with self.session.client(
            "cur",
            region_name="us-east-1",  # CUR is global but uses us-east-1 endpoint
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as cur:
            try:
                # 4. Create CUR Report Definition
                report_name = f"valdrix-cur-{self.credentials.account_id}"
                await cur.put_report_definition(
                    ReportDefinition={
                        "ReportName": report_name,
                        "TimeUnit": "HOURLY",
                        "Format": "Parquet",
                        "Compression": "GZIP",
                        "AdditionalSchemaElements": ["RESOURCES"],
                        "S3Bucket": self.bucket_name,
                        "S3Prefix": "cur",
                        "S3Region": self._resolved_region,
                        "ReportVersioning": "OVERWRITE_REPORT",
                        "RefreshClosedReports": True,
                    }
                )

                return {
                    "status": "success",
                    "bucket_name": self.bucket_name,
                    "report_name": report_name,
                }
            except Exception as e:
                logger.error("cur_setup_failed", error=str(e))
                return {"status": "error", "message": f"CUR setup failed: {str(e)}"}

    async def get_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Materialized interface for cost ingestion."""
        # Convert to date for internal processing
        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date

        summary = await self.get_daily_costs(s_date, e_date)
        return [r.model_dump() for r in summary.records]

    async def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        usage_only: bool = False,
        group_by_service: bool = True,
    ) -> CloudUsageSummary:
        """
        Fetch daily costs from CUR files in S3 for a specific date range.
        Consolidates logic from previous CUR and S3 adapters.
        """
        try:
            # 1. Discover relevant Parquet files
            report_files = await self._list_cur_files_in_range(start_date, end_date)
            
            if not report_files:
                logger.warning(
                    "no_cur_files_found_in_range",
                    bucket=self.bucket_name,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                return self._empty_summary()

            # 2. Process and aggregate
            return await self._process_files_in_range(
                report_files, start_date, end_date
            )

        except Exception as e:
            logger.error("cur_daily_costs_failed", error=str(e))
            raise

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> List[Dict[str, Any]]:
        """
        CUR adapters do not typically discover live resources; they process
        historical billing records. Use AWSAdapter for live discovery.
        """
        return []

    async def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Efficiently stream cost data without loading full summary into memory.
        """
        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date
        
        report_files = await self._list_cur_files_in_range(s_date, e_date)
        
        for file_key in report_files:
            # We process one file at a time and yield records
            file_summary = await self._ingest_single_file(file_key, s_date, e_date)
            for record in file_summary.records:
                yield {
                    "timestamp": record.date,
                    "service": record.service,
                    "region": record.region,
                    "cost_usd": record.amount,
                    "currency": record.currency,
                    "amount_raw": record.amount_raw,
                    "usage_type": record.usage_type,
                    "tags": record.tags,
                    "source_adapter": "cur_data_export",
                }

    async def _list_cur_files_in_range(self, start_date: date, end_date: date) -> List[str]:
        """
        Lists S3 keys for CUR Parquet files representing the date range.
        Handles the year/month subdirectory structure and manifest files.
        """
        creds = await self._get_credentials()
        prefix_base = self.credentials.cur_prefix or "cur"
        files: List[str] = []
        seen: set[str] = set()

        async with self.session.client(
            "s3",
            region_name=self._resolved_region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            # Traversal logic: Scan each month in the range
            current = start_date.replace(day=1)
            while current <= end_date:
                month_prefix = f"{prefix_base}/{current.year}/{current.month:02d}/"
                
                paginator = s3.get_paginator("list_objects_v2")
                manifest_keys = []
                parquet_keys = []
                
                async for page in paginator.paginate(
                    Bucket=self.bucket_name, Prefix=month_prefix
                ):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.lower().endswith("manifest.json"):
                            manifest_keys.append((obj.get("LastModified"), key))
                        elif key.lower().endswith(".parquet"):
                            parquet_keys.append(key)

                # Prioritize manifest files if found (more reliable set of parts)
                if manifest_keys:
                    manifest_keys.sort(key=lambda x: x[0] or datetime.min, reverse=True)
                    latest_manifest = manifest_keys[0][1]
                    try:
                        manifest_obj = await s3.get_object(Bucket=self.bucket_name, Key=latest_manifest)
                        manifest_data = json.loads(await manifest_obj["Body"].read())
                        for r_key in manifest_data.get("reportKeys", []):
                            if r_key.endswith(".parquet") and r_key not in seen:
                                files.append(r_key)
                                seen.add(r_key)
                    except Exception as e:
                        logger.warning("manifest_parse_failed", key=latest_manifest, error=str(e))
                        # Fallback to direct listing
                        for pk in parquet_keys:
                            if pk not in seen:
                                files.append(pk)
                                seen.add(pk)
                else:
                    for pk in parquet_keys:
                        if pk not in seen:
                            files.append(pk)
                            seen.add(pk)

                # Increment month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
        
        return files

    async def _process_files_in_range(
        self, files: List[str], start_date: date, end_date: date
    ) -> CloudUsageSummary:
        """Processes multiple files and aggregates into a single summary."""
        master_summary = self._empty_summary()
        master_summary.start_date = start_date
        master_summary.end_date = end_date
        per_file_record_cap = 10000
        truncated_records_total = 0
        
        for file_key in files:
            file_summary = await self._ingest_single_file(file_key, start_date, end_date)
            
            # Merge aggregations
            master_summary.total_cost += file_summary.total_cost
            retained_records = file_summary.records[:per_file_record_cap]
            master_summary.records.extend(retained_records)
            truncated_count = max(0, len(file_summary.records) - len(retained_records))
            if truncated_count > 0:
                truncated_records_total += truncated_count
                logger.warning(
                    "cur_file_summary_records_truncated",
                    file_key=file_key,
                    cap=per_file_record_cap,
                    truncated_records=truncated_count,
                )
            
            for k, v in file_summary.by_service.items():
                master_summary.by_service[k] = master_summary.by_service.get(k, Decimal("0")) + v
            for k, v in file_summary.by_region.items():
                master_summary.by_region[k] = master_summary.by_region.get(k, Decimal("0")) + v
                
            for tk, tag_map in file_summary.by_tag.items():
                if tk not in master_summary.by_tag:
                    master_summary.by_tag[tk] = {}
                for tv, tcost in tag_map.items():
                    master_summary.by_tag[tk][tv] = master_summary.by_tag[tk].get(tv, Decimal("0")) + tcost

        if truncated_records_total > 0:
            logger.warning(
                "cur_master_summary_records_truncated",
                cap_per_file=per_file_record_cap,
                truncated_records_total=truncated_records_total,
                files_processed=len(files),
            )
                    
        return master_summary

    async def _ingest_single_file(self, key: str, start_date: date, end_date: date) -> CloudUsageSummary:
        """Downloads and processes a single Parquet file."""
        creds = await self._get_credentials()
        async with self.session.client(
            "s3",
            region_name=self._resolved_region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
                tmp_path = tmp.name
                try:
                    obj = await s3.get_object(Bucket=self.bucket_name, Key=key)
                    async with obj["Body"] as stream:
                        while True:
                            chunk = await stream.read(1024 * 1024 * 16) # 16MB chunks
                            if not chunk:
                                break
                            tmp.write(chunk)
                    
                    return self._process_parquet_streamingly(tmp_path, start_date, end_date)
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

    def _process_parquet_streamingly(self, file_path: str, start_date: date | None = None, end_date: date | None = None) -> CloudUsageSummary:
        """
        Processes a Parquet file using row groups to keep memory low.
        Aggregates metrics on the fly with optional date filtering.
        """
        parquet_file = pq.ParquetFile(file_path)

        # Initialize Summary
        total_cost_usd = Decimal("0")
        by_service: dict[str, Decimal] = {}
        by_region: dict[str, Decimal] = {}
        by_tag: dict[str, dict[str, Decimal]] = {}
        all_records: list[CostRecord] = []
        record_cap = max(1, int(getattr(self, "_SUMMARY_RECORD_CAP", 50000)))
        dropped_records = 0

        min_date_found = None
        max_date_found = None

        # AWS CUR Column Aliases
        CUR_COLUMNS = {
            "date": ["lineItem/UsageStartDate", "identity/TimeInterval", "line_item_usage_start_date"],
            "cost": ["lineItem/UnblendedCost", "line_item_unblended_cost", "lineItem/AmortizedCost", "line_item_amortized_cost"],
            "currency": ["lineItem/CurrencyCode", "line_item_currency_code"],
            "service": ["lineItem/ProductCode", "line_item_product_code", "product/ProductName"],
            "region": ["product/region", "lineItem/AvailabilityZone", "product/location"],
            "usage_type": ["lineItem/UsageType", "line_item_operation"],
        }

        for i in range(parquet_file.num_row_groups):
            try:
                table = parquet_file.read_row_group(i)
                df_chunk = table.to_pandas()
            except Exception as e:
                logger.warning("cur_row_group_read_failed", error=str(e), row_group=i)
                continue

            if df_chunk.empty:
                continue

            col_map = {k: next((c for c in v if c in df_chunk.columns), None) for k, v in CUR_COLUMNS.items()}
            if not col_map.get("date") or not col_map.get("cost"):
                continue

            # Date Range check for optimization
            df_chunk[col_map["date"]] = pd.to_datetime(df_chunk[col_map["date"]])
            chunk_min = df_chunk[col_map["date"]].min().date()
            chunk_max = df_chunk[col_map["date"]].max().date()
            
            if start_date and chunk_max < start_date:
                continue
            if end_date and chunk_min > end_date:
                continue

            min_date_found = min(min_date_found, chunk_min) if min_date_found else chunk_min
            max_date_found = max(max_date_found, chunk_max) if max_date_found else chunk_max

            for _, row in df_chunk.iterrows():
                row_date = row[col_map["date"]].date()
                if start_date and row_date < start_date:
                    continue
                if end_date and row_date > end_date:
                    continue

                try:
                    record = self._parse_row(row, col_map)
                    if len(all_records) < record_cap:
                        all_records.append(record)
                    else:
                        dropped_records += 1

                    total_cost_usd += record.amount
                    svc = record.service or "Unknown"
                    reg = record.region or "Unknown"
                    by_service[svc] = by_service.get(svc, Decimal("0")) + record.amount
                    by_region[reg] = by_region.get(reg, Decimal("0")) + record.amount

                    for tk, tv in record.tags.items():
                        if tk not in by_tag:
                            by_tag[tk] = {}
                        by_tag[tk][tv] = by_tag[tk].get(tv, Decimal("0")) + record.amount
                except Exception:
                    continue

        if dropped_records > 0:
            logger.warning(
                "cur_summary_record_cap_reached",
                cap=record_cap,
                dropped_records=dropped_records,
                retained_records=len(all_records),
                start=str(start_date) if start_date else None,
                end=str(end_date) if end_date else None,
            )

        return CloudUsageSummary(
            tenant_id="anonymous",
            provider="aws",
            start_date=min_date_found or date.today(),
            end_date=max_date_found or date.today(),
            total_cost=total_cost_usd,
            records=all_records,
            by_service=by_service,
            by_region=by_region,
            by_tag=by_tag,
        )

    def _parse_row(self, row: pd.Series, col_map: Dict[str, str | None]) -> CostRecord:
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
        currency = (
            "USD" if pd.isna(currency_val) or currency_val == "" else str(currency_val)
        )

        service_key = col_map.get("service")
        service_val = row.get(service_key, "Unknown") if service_key else "Unknown"
        service = (
            "Unknown" if pd.isna(service_val) or service_val == "" else str(service_val)
        )

        region_key = col_map.get("region")
        region_val = row.get(region_key, "Global") if region_key else "Global"
        region = (
            "Global" if pd.isna(region_val) or region_val == "" else str(region_val)
        )

        usage_key = col_map.get("usage_type")
        usage_val = row.get(usage_key, "Unknown") if usage_key else "Unknown"
        usage_type = (
            "Unknown" if pd.isna(usage_val) or usage_val == "" else str(usage_val)
        )

        tags = self._extract_tags(row)

        # Use raw datetime to preserve hourly granularity
        date_column = col_map["date"]
        if not date_column:
            raise ConfigurationError("Missing date column mapping")
        dt = pd.to_datetime(row[date_column])
        if pd.isna(dt):
            raise ConfigurationError("Invalid usage start date")
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
            tags=tags,
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

    async def _get_credentials(self) -> dict[str, str]:
        """Helper to get credentials from existing adapter logic or shared util."""
        # For simplicity, we assume the credentials logic is shared or we re-implement
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter

        adapter = MultiTenantAWSAdapter(self.credentials)
        credentials = await adapter.get_credentials()
        return cast(dict[str, str], credentials)

    def _empty_summary(self) -> CloudUsageSummary:
        return CloudUsageSummary(
            tenant_id="anonymous", # Decoupled from tenant model in adapter
            provider="aws",
            start_date=date.today(),
            end_date=date.today(),
            total_cost=Decimal("0"),
            records=[],
            by_service={},
            by_region={},
        )

    async def get_resource_usage(
        self, service_name: str, resource_id: str | None = None
    ) -> List[Dict[str, Any]]:
        """
        Detailed usage metrics are parsed from the CUR records during ingestion.
        """
        return []
