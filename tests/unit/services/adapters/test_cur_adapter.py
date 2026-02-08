"""
Tests for CURAdapter - AWS CUR ingestion from S3
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
import pandas as pd
from botocore.exceptions import ClientError
from app.shared.adapters.cur_adapter import CURAdapter, CURConfig


@pytest.fixture
def cur_adapter():
    return CURAdapter(
        bucket_name="test-bucket",
        report_prefix="cur",
        credentials={"AccessKeyId": "key", "SecretAccessKey": "secret"},
        region="us-east-1"
    )


@pytest.mark.asyncio
async def test_verify_connection_success(cur_adapter):
    """Test verify_connection returns True on success."""
    with patch.object(cur_adapter.session, "client") as mock_client:
        mock_s3 = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_s3
        mock_s3.head_bucket.return_value = {}
        
        assert await cur_adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_verify_connection_failure(cur_adapter):
    """Test verify_connection returns False on ClientError."""
    with patch.object(cur_adapter.session, "client") as mock_client:
        mock_s3 = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_s3
        mock_s3.head_bucket.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadBucket")
        
        assert await cur_adapter.verify_connection() is False


@pytest.mark.asyncio
async def test_list_cur_files(cur_adapter):
    """Test _list_cur_files iterates through months and paginates."""
    start = date(2026, 1, 30)
    end = date(2026, 2, 2)
    
    with patch.object(cur_adapter.session, "client") as mock_client:
        mock_s3 = MagicMock() # Use MagicMock for client
        mock_client.return_value.__aenter__.return_value = mock_s3
        
        # Mock paginator
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        
        # Paginated results
        mock_pages = [
            {"Contents": [{"Key": "cur/2026/01/f1.parquet"}]},
            {"Contents": [{"Key": "cur/2026/02/f2.parquet"}]}
        ]
        
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

        def mock_paginate(**kwargs):
            if "01" in kwargs["Prefix"]:
                return MockAsyncIterator([mock_pages[0]])
            else:
                return MockAsyncIterator([mock_pages[1]])
                
        mock_paginator.paginate = mock_paginate
        
        files = await cur_adapter._list_cur_files(start, end)
        
        assert "cur/2026/01/f1.parquet" in files
        assert "cur/2026/02/f2.parquet" in files
        assert len(files) == 2


@pytest.mark.asyncio
async def test_parse_cur_files_success(cur_adapter):
    """Test _parse_cur_files reads and aggregates data."""
    files = ["f1.parquet"]
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)
    
    # Mock row data
    df_data = pd.DataFrame({
        "line_item_usage_start_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
        "line_item_product_code": ["S3", "EC2", "S3"],
        "line_item_blended_cost": [1.0, 2.0, 3.0]
    })
    
    with patch.object(cur_adapter.session, "client") as mock_client:
        mock_s3 = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_s3
        
        mock_body = AsyncMock()
        mock_body.read.return_value = b"fake-parquet-content"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_body.__aenter__.return_value = mock_body
        
        with patch.object(pd, "read_parquet", return_value=df_data):
            # 1. Without group_by
            results = await cur_adapter._parse_cur_files(files, start, end, group_by_service=False)
            assert len(results) == 2  # 2 days
            assert any(r["cost"] == 3.0 for r in results) # Jan 1: 1+2=3
            
            # 2. With group_by
            results = await cur_adapter._parse_cur_files(files, start, end, group_by_service=True)
            assert len(results) == 3 # Jan 1 S3, Jan 1 EC2, Jan 2 S3
            assert any(r["service"] == "EC2" and r["cost"] == 2.0 for r in results)


def test_cur_config_from_dict():
    """Test CURConfig.from_dict."""
    data = {
        "bucket_name": "b",
        "report_prefix": "p",
        "report_name": "n",
        "format": "Parquet"
    }
    config = CURConfig.from_dict(data)
    assert config.bucket_name == "b"
    assert config.format == "Parquet"
