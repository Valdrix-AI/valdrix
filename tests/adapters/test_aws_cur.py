import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
import uuid

from app.shared.adapters.aws_cur import AWSCURAdapter
from app.models.aws_connection import AWSConnection
from app.schemas.costs import CloudUsageSummary, CostRecord

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
    mock_s3 = MagicMock()
    
    # Mock paginator response
    page = {
        "Contents": [
            {"Key": "cur/report-202310.parquet", "LastModified": datetime(2023, 10, 2)}
        ]
    }
    class MockAsyncIterator:
        def __init__(self, pages):
            self.pages = pages
            self.idx = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.idx >= len(self.pages):
                raise StopAsyncIteration
            val = self.pages[self.idx]
            self.idx += 1
            return val
    mock_paginator = MagicMock()
    mock_paginator.paginate = lambda **kwargs: MockAsyncIterator([page])
    mock_s3.get_paginator.return_value = mock_paginator
    
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

    mock_s3.get_object = AsyncMock(return_value={"Body": MockStream(parquet_bytes)})

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


@pytest.mark.asyncio
async def test_verify_connection_success():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    mock_s3 = MagicMock()
    mock_s3.head_bucket = AsyncMock(return_value={})

    with patch("aioboto3.Session") as MockSession, \
         patch.object(AWSCURAdapter, "_get_credentials", return_value={
            "AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"
         }):
        session_instance = MockSession.return_value
        session_instance.client.return_value.__aenter__.return_value = mock_s3

        adapter = AWSCURAdapter(conn)
        assert await adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_verify_connection_failure():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    mock_s3 = MagicMock()
    mock_s3.head_bucket = AsyncMock(side_effect=Exception("no access"))

    with patch("aioboto3.Session") as MockSession, \
         patch.object(AWSCURAdapter, "_get_credentials", return_value={
            "AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"
         }):
        session_instance = MockSession.return_value
        session_instance.client.return_value.__aenter__.return_value = mock_s3

        adapter = AWSCURAdapter(conn)
        assert await adapter.verify_connection() is False


@pytest.mark.asyncio
async def test_ingest_latest_parquet_no_files():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    mock_s3 = MagicMock()
    page = {"Contents": [{"Key": "cur/manifest.json", "LastModified": datetime(2023, 10, 2)}]}
    class MockAsyncIterator:
        def __init__(self, pages):
            self.pages = pages
            self.idx = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.idx >= len(self.pages):
                raise StopAsyncIteration
            val = self.pages[self.idx]
            self.idx += 1
            return val
    mock_paginator = MagicMock()
    mock_paginator.paginate = lambda **kwargs: MockAsyncIterator([page])
    mock_s3.get_paginator.return_value = mock_paginator

    with patch("aioboto3.Session") as MockSession, \
         patch.object(AWSCURAdapter, "_get_credentials", return_value={
            "AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"
         }):
        session_instance = MockSession.return_value
        session_instance.client.return_value.__aenter__.return_value = mock_s3

        adapter = AWSCURAdapter(conn)
        summary = await adapter.ingest_latest_parquet()
        assert isinstance(summary, CloudUsageSummary)
        assert summary.total_cost == Decimal("0")


def test_parse_row_handles_invalid_cost_and_date():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    adapter = AWSCURAdapter(conn)
    row = pd.Series({
        "lineItem/UsageStartDate": "not-a-date",
        "lineItem/UnblendedCost": "nan",
    })
    col_map = {
        "date": "lineItem/UsageStartDate",
        "cost": "lineItem/UnblendedCost",
        "currency": "currency",
        "service": "service",
        "region": "region",
        "usage_type": "usage_type",
    }

    with pytest.raises(ValueError):
        adapter._parse_row(row, col_map)


def test_process_parquet_missing_required_columns():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    adapter = AWSCURAdapter(conn)

    class FakeTable:
        def to_pandas(self):
            return pd.DataFrame({"foo": [1, 2, 3]})

    class FakeParquet:
        num_row_groups = 1
        def read_row_group(self, _i):
            return FakeTable()

    with patch("app.shared.adapters.aws_cur.pq.ParquetFile", return_value=FakeParquet()):
        summary = adapter._process_parquet_streamingly("dummy.parquet")
        assert summary.total_cost == Decimal("0")
        assert summary.records == []


def test_process_parquet_partial_row_groups():
    conn = AWSConnection(
        tenant_id=uuid.uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-test",
        region="us-east-1"
    )
    adapter = AWSCURAdapter(conn)

    class FakeTable:
        def to_pandas(self):
            return pd.DataFrame({
                "lineItem/UsageStartDate": [datetime(2023, 10, 1, tzinfo=timezone.utc)],
                "lineItem/UnblendedCost": [5.0],
                "lineItem/CurrencyCode": ["USD"],
                "lineItem/ProductCode": ["AmazonEC2"],
                "product/region": ["us-east-1"],
                "lineItem/UsageType": ["BoxUsage:t3.medium"],
            })

    class FakeParquet:
        num_row_groups = 2
        def read_row_group(self, i):
            if i == 0:
                raise ValueError("corrupt row group")
            return FakeTable()

    with patch("app.shared.adapters.aws_cur.pq.ParquetFile", return_value=FakeParquet()):
        summary = adapter._process_parquet_streamingly("dummy.parquet")
        assert len(summary.records) == 1
        assert summary.total_cost == Decimal("5.0")
