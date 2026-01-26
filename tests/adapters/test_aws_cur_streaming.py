import pytest
import pandas as pd
import io
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from datetime import datetime
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.models.aws_connection import AWSConnection
from app.schemas.costs import CloudUsageSummary

# Mock data
MOCK_CUR_DATA = {
    "lineItem/UsageStartDate": [datetime(2023, 10, 1)] * 5,
    "lineItem/UnblendedCost": [1.0] * 5,
    "lineItem/CurrencyCode": ["USD"] * 5,
    "lineItem/ProductCode": ["AmazonEC2", "AmazonS3", "AmazonRDS", "AmazonLambda", "AmazonVPC"],
    "product/region": ["us-east-1"] * 5,
    "lineItem/UsageType": ["Usage"] * 5,
    "resourceTags/user:Project": ["P1", "P2", "P3", "P4", "P5"]
}

class MockStream:
    def __init__(self, data):
        self.data = data
        self.offset = 0
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    async def read(self, amt):
        chunk = self.data[self.offset : self.offset + amt]
        self.offset += len(chunk)
        return chunk

@pytest.mark.asyncio
async def test_ingest_latest_parquet_streaming():
    # 1. Create a mock connection
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        region="us-east-1"
    )

    # 2. Prepare Parquet Bytes
    df = pd.DataFrame(MOCK_CUR_DATA)
    parquet_buffer = io.BytesIO()
    # Write as multiple row groups to test chunked reading
    # PyArrow engine supports row_group_size
    df.to_parquet(parquet_buffer, row_group_size=2, engine="pyarrow")
    parquet_bytes = parquet_buffer.getvalue()

    # 3. Mock S3 Client
    mock_s3 = AsyncMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "cur/test.parquet", "LastModified": datetime.now()}]
    }
    
    mock_s3.get_object.return_value = {"Body": MockStream(parquet_bytes)}

    # 4. Patch aioboto3.Session and _get_credentials
    with patch("aioboto3.Session") as MockSession:
        session_instance = MockSession.return_value
        session_instance.client.return_value.__aenter__.return_value = mock_s3
        
        with patch.object(AWSCURAdapter, "_get_credentials", return_value={
            "AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"
        }):
            adapter = AWSCURAdapter(conn)
            summary = await adapter.ingest_latest_parquet()
            
            # Assertions
            assert isinstance(summary, CloudUsageSummary)
            assert summary.total_cost == Decimal("5.0")
            assert len(summary.records) == 5
            assert summary.by_service["AmazonEC2"] == Decimal("1.0")
            assert summary.by_service["AmazonS3"] == Decimal("1.0")
            
            # Check if tags were extracted
            assert summary.records[0].tags["Project"] == "P1"
            assert summary.by_tag["Project"]["P1"] == Decimal("1.0")

            # Verify temporary file cleanup (indirectly if it didn't fail)
            # The test would crash if it tried to read a non-existent file
