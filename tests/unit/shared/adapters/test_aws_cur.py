import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.core.credentials import AWSCredentials

@pytest.fixture
def mock_creds():
    return AWSCredentials(
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
        external_id="ext-id",
        region="us-east-1"
    )

@pytest.mark.asyncio
class TestAWSCURAdapter:
    async def test_setup_cur_automation_creates_bucket_and_report(self, mock_creds):
        # Mock aioboto3 session and clients
        mock_s3 = AsyncMock()
        mock_cur = AsyncMock()
        
        # Mock S3 head_bucket to raise 404 (bucket doesn't exist)
        from botocore.exceptions import ClientError
        mock_s3.head_bucket.side_effect = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")
        
        # Mock session.client context manager
        mock_s3_ctx = MagicMock()
        mock_s3_ctx.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3_ctx.__aexit__ = AsyncMock()
        
        mock_cur_ctx = MagicMock()
        mock_cur_ctx.__aenter__ = AsyncMock(return_value=mock_cur)
        mock_cur_ctx.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.client.side_effect = [mock_s3_ctx, mock_cur_ctx]

        # Patch credentials helper
        with patch.object(AWSCURAdapter, "_get_credentials", new=AsyncMock(return_value={
            "AccessKeyId": "AKIA...", "SecretAccessKey": "SECRET", "SessionToken": "TOKEN"
        })):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            
            result = await adapter.setup_cur_automation()
            
            assert result["status"] == "success"
            assert result["bucket_name"] == adapter.bucket_name
            
            # Verify bucket creation
            mock_s3.create_bucket.assert_awaited_once()
            mock_s3.put_bucket_policy.assert_awaited_once()
            
            # Verify CUR definition
            mock_cur.put_report_definition.assert_awaited_once()
            call_args = mock_cur.put_report_definition.call_args[1]
            assert call_args["ReportDefinition"]["ReportName"] == f"valdrix-cur-{mock_creds.account_id}"

    async def test_verify_connection_success(self, mock_creds):
        mock_s3 = AsyncMock()
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_context.__aexit__ = AsyncMock()
        
        mock_session = MagicMock()
        mock_session.client.return_value = mock_context
        
        with patch.object(AWSCURAdapter, "_get_credentials", new=AsyncMock(return_value={
            "AccessKeyId": "test", "SecretAccessKey": "test", "SessionToken": "test"
        })):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            
            success = await adapter.verify_connection()
            assert success is True
            mock_s3.head_bucket.assert_awaited_with(Bucket=adapter.bucket_name)

    async def test_process_parquet_streamingly_logs_when_record_cap_exceeded(self, mock_creds):
        adapter = AWSCURAdapter(mock_creds)
        adapter._SUMMARY_RECORD_CAP = 2

        df = pd.DataFrame(
            {
                "lineItem/UsageStartDate": [
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T01:00:00Z",
                    "2026-02-01T02:00:00Z",
                ],
                "lineItem/UnblendedCost": ["1.0", "2.0", "3.0"],
                "lineItem/CurrencyCode": ["USD", "USD", "USD"],
                "lineItem/ProductCode": ["AmazonEC2", "AmazonEC2", "AmazonEC2"],
                "product/region": ["us-east-1", "us-east-1", "us-east-1"],
                "lineItem/UsageType": ["BoxUsage", "BoxUsage", "BoxUsage"],
            }
        )

        class _FakeTable:
            def to_pandas(self):
                return df

        class _FakeParquetFile:
            num_row_groups = 1

            def read_row_group(self, idx):
                assert idx == 0
                return _FakeTable()

        with patch(
            "app.shared.adapters.aws_cur.pq.ParquetFile",
            return_value=_FakeParquetFile(),
        ), patch("app.shared.adapters.aws_cur.logger.warning") as mock_warning:
            summary = adapter._process_parquet_streamingly("/tmp/cur.parquet")

        assert len(summary.records) == 2
        assert summary.total_cost == 6
        mock_warning.assert_any_call(
            "cur_summary_record_cap_reached",
            cap=2,
            dropped_records=1,
            retained_records=2,
            start=None,
            end=None,
        )
