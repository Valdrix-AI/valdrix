import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch
from botocore.exceptions import ClientError
from app.shared.connections.cur_automation import IAMCURManager
from app.models.aws_connection import AWSConnection


@pytest.mark.asyncio
async def test_iam_cur_manager_setup_success():
    # 1. Setup mock connection
    conn = AWSConnection(
        id=uuid.uuid4(),
        aws_account_id="123456789012",
        region="us-east-1",
        role_arn="arn:aws:iam::123456789012:role/ValdrixReadOnly",
        external_id="vx-test",
    )

    # 2. Mock Boto3 Clients
    mock_s3 = AsyncMock()
    mock_cur = AsyncMock()

    # Mock head_bucket returning 404 (bucket doesn't exist)
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "head_bucket"
    )

    # 3. Patch aioboto3 and _get_credentials
    with patch("aioboto3.Session") as MockSession:
        session_instance = MockSession.return_value

        session_instance.client.side_effect = None

        # Simplified Client Mocking for easier testing
        class MockContextManager:
            def __init__(self, client):
                self.client = client

            async def __aenter__(self):
                return self.client

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        session_instance.client.side_effect = lambda s, **k: MockContextManager(
            mock_s3 if s == "s3" else mock_cur
        )

        with patch.object(
            IAMCURManager,
            "_get_credentials",
            return_value={
                "AccessKeyId": "fake",
                "SecretAccessKey": "fake",
                "SessionToken": "fake",
            },
        ):
            manager = IAMCURManager(conn)
            result = await manager.setup_cur_automation()

            # 4. Assertions
            assert result["status"] == "success"
            assert "valdrix-cur-123456789012-us-east-1" in result["bucket_name"]

            # Verify S3 methods called
            mock_s3.create_bucket.assert_called_once()
            mock_s3.put_bucket_policy.assert_called_once()

            # Verify CUR method called
            mock_cur.put_report_definition.assert_called_once()

            # Check Policy Content
            args, kwargs = mock_s3.put_bucket_policy.call_args
            policy = json.loads(kwargs["Policy"])
            assert (
                policy["Statement"][0]["Principal"]["Service"]
                == "billingreports.amazonaws.com"
            )
            assert (
                "s3:PutObject"
                in [
                    s["Action"]
                    for s in policy["Statement"]
                    if "AllowCURPutObject" in s["Sid"]
                ][0]
            )


@pytest.mark.asyncio
async def test_iam_cur_manager_bucket_exists():
    conn = AWSConnection(aws_account_id="123456789012", region="us-east-1")
    mock_s3 = AsyncMock()
    mock_cur = AsyncMock()

    # head_bucket succeeds (bucket exists)
    mock_s3.head_bucket.return_value = {}

    with patch("aioboto3.Session") as MockSession:
        session_instance = MockSession.return_value

        class MockContextManager:
            def __init__(self, client):
                self.client = client

            async def __aenter__(self):
                return self.client

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        session_instance.client.side_effect = lambda s, **k: MockContextManager(
            mock_s3 if s == "s3" else mock_cur
        )

        with patch.object(
            IAMCURManager,
            "_get_credentials",
            return_value={
                "AccessKeyId": "fake",
                "SecretAccessKey": "fake",
                "SessionToken": "fake",
            },
        ):
            manager = IAMCURManager(conn)
            await manager.setup_cur_automation()

            mock_s3.create_bucket.assert_not_called()
            mock_s3.put_bucket_policy.assert_called_once()
