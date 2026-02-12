import io
import pandas as pd
import aioboto3
import structlog
from typing import Any, cast
from app.models.aws_connection import AWSConnection

logger = structlog.get_logger()

class S3ParquetAdapter:
    """
    Adapter for reading AWS Cost and Usage Reports (CUR) in Parquet format from S3.
    Provides SKU-level precision. Uses streaming row-group reads when pyarrow is available.
    Falls back to in-memory reads when pyarrow is not installed.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self.session = aioboto3.Session()

    async def fetch_cur_data(self, s3_path: str) -> pd.DataFrame:
        """
        Download a Parquet file from S3 and return as a pandas DataFrame.
        s3_path: full S3 URI or bucket + key
        """
        if s3_path.startswith("s3://"):
            bucket, key = s3_path.replace("s3://", "").split("/", 1)
        else:
            # Assume it's just the key if bucket is known, but better to be explicit
            bucket = f"valdrix-cur-{self.connection.aws_account_id}-{self.connection.region}"
            key = s3_path

        creds = await self._get_credentials()
        
        try:
            import pyarrow.parquet as pq
            import pyarrow.fs as pafs
            use_pyarrow = True
        except ImportError:
            use_pyarrow = False

        if use_pyarrow:
            try:
                s3fs = pafs.S3FileSystem(
                    access_key=creds["AccessKeyId"],
                    secret_key=creds["SecretAccessKey"],
                    session_token=creds.get("SessionToken"),
                    region=self.connection.region
                )
                path = f"{bucket}/{key}"
                with s3fs.open_input_file(path) as f:
                    parquet_file = pq.ParquetFile(f)
                    batches = [batch.to_pandas() for batch in parquet_file.iter_batches()]
                df = pd.concat(batches, ignore_index=True) if batches else pd.DataFrame()
                logger.info("cur_parquet_read_success", bucket=bucket, key=key, rows=len(df))
                return df
            except Exception as e:
                logger.warning(
                    "cur_parquet_stream_read_failed_fallback",
                    bucket=bucket,
                    key=key,
                    error=str(e)
                )

        async with self.session.client(
            "s3",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            try:
                response = await s3.get_object(Bucket=bucket, Key=key)
                content = await response["Body"].read()

                # Use pandas to read parquet from memory buffer (fallback path)
                df = pd.read_parquet(io.BytesIO(content))
                logger.info("cur_parquet_read_success", bucket=bucket, key=key, rows=len(df))
                return df
            except Exception as e:
                logger.error("cur_parquet_read_failed", bucket=bucket, key=key, error=str(e))
                raise

    async def _get_credentials(self) -> dict[str, str]:
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        adapter = MultiTenantAWSAdapter(self.connection)
        credentials = await adapter.get_credentials()
        return cast(dict[str, str], credentials)

    def process_dataframe(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Map CUR 2.0 / Data Export columns to Valdrix CostRecord format.
        """
        # Column mapping (standard AWS CUR 2.0)
        # Note: Actual column names might vary slightly depending on export settings
        mapping = {
            "line_item_usage_start_date": "timestamp",
            "line_item_usage_account_id": "account_id",
            "line_item_product_code": "service",
            "line_item_operation": "usage_type",
            "line_item_unblended_cost": "unblended_cost",
            "line_item_amortized_cost": "cost_usd", # We prefer Amortized
            "product_region": "region",
        }

        # Filter and rename
        existing_cols = [c for c in mapping.keys() if c in df.columns]
        df_subset = df[existing_cols].rename(columns={k: v for k, v in mapping.items() if k in existing_cols})

        # Ensure types
        if "timestamp" in df_subset.columns:
            df_subset["timestamp"] = pd.to_datetime(df_subset["timestamp"])
            df_subset["recorded_at"] = df_subset["timestamp"].dt.date
        
        # Convert to list of dicts for bulk insert
        records = df_subset.to_dict("records")
        return cast(list[dict[str, Any]], records)
