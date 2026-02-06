import pytest
import pandas as pd
import io
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from datetime import datetime
import uuid

from app.shared.adapters.aws_cur import AWSCURAdapter
from app.models.aws_connection import AWSConnection
from app.schemas.costs import CloudUsageSummary

# Mock data
MOCK_CUR_DATA = {
    "lineItem/UsageStartDate": [datetime(2023, 10, 1), datetime(2023, 10, 1)],
    "lineItem/UnblendedCost": [10.50, 20.00],
    "lineItem/CurrencyCode": ["USD", "EUR"],
    "lineItem/ProductCode": ["AmazonEC2", "AmazonRDS"],
    "product/region": ["us-east-1", "eu-west-1"],
    "lineItem/UsageType": ["BoxUsage:t3.medium", "InstanceUsage:db.t3.small"],
    "resourceTags/user:Project": ["Alpha", "Beta"],
    "resourceTags/user:Environment": ["Prod", "Dev"]
}

@pytest.mark.asyncio
async def test_ingest_latest_parquet():
    # 1. Create a mock connection
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )

    # 2. Mock S3 Client and Session
    mock_s3 = AsyncMock()
    
    # Mock list_objects_v2 response
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "cur/report-202310.parquet", "LastModified": datetime(2023, 10, 2)}
        ]
    }
    
    # Mock/Simulate Parquet download
    df = pd.DataFrame(MOCK_CUR_DATA)
    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer)
    parquet_buffer.seek(0)  # Reset buffer position to beginning
    parquet_bytes = parquet_buffer.getvalue()
    
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

    mock_s3.get_object.return_value = {"Body": MockStream(parquet_bytes)}

    # 3. Patch aioboto3.Session
    with patch("aioboto3.Session") as MockSession:
        session_instance = MockSession.return_value
        session_instance.client.return_value.__aenter__.return_value = mock_s3
        
        # Patch _get_credentials since it tries to instantiate MultiTenantAWSAdapter
        with patch.object(AWSCURAdapter, "_get_credentials", return_value={
            "AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"
        }):
            adapter = AWSCURAdapter(conn)
            summary = await adapter.ingest_latest_parquet()
            
            # Assertions
            assert isinstance(summary, CloudUsageSummary)
            assert summary.total_cost == Decimal("30.50") # 10.50 + 20.00 (Assuming 1:1 for MVP)
            
            assert len(summary.records) == 2
            
            # Record 1 (EC2, USD)
            r1 = summary.records[0]
            assert r1.service == "AmazonEC2"
            assert r1.currency == "USD"
            assert r1.amount == Decimal("10.50")
            assert r1.tags["Project"] == "Alpha"
            assert r1.tags["Environment"] == "Prod"
            
            # Record 2 (RDS, EUR)
            r2 = summary.records[1]
            assert r2.service == "AmazonRDS"
            assert r2.currency == "EUR"
            assert r2.amount == Decimal("20.00") # Raw amount stored
            assert r2.tags["Project"] == "Beta"
            assert r2.tags["Environment"] == "Dev"

            # Check aggregations
            assert summary.by_service["AmazonEC2"] == Decimal("10.50")
            assert summary.by_service["AmazonRDS"] == Decimal("20.00")
            assert summary.by_region["us-east-1"] == Decimal("10.50")
            assert summary.by_region["eu-west-1"] == Decimal("20.00")

