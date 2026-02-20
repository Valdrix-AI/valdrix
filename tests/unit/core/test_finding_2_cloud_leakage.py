import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.shared.core.cloud_connection import CloudConnectionService
from app.shared.core.exceptions import AdapterError


@pytest.mark.asyncio
async def test_verify_connection_sanitizes_raw_exceptions():
    """
    Finding #2: AdapterError sanitizes raw cloud provider exceptions.
    Verifies that sensitive info (ARNs, account IDs, secret keys) is NOT
    exposed to the API consumer.
    """
    mock_db = AsyncMock()
    service = CloudConnectionService(mock_db)
    tenant_id = uuid4()

    connection = MagicMock()
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.status = "pending"

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    raw_error = (
        "AWS Error: AccessDenied for arn:aws:iam::123456789012:user/admin "
        "with SecretKey=ABC12345"
    )
    mock_adapter.verify_connection.side_effect = Exception(raw_error)

    with patch(
        "app.shared.core.cloud_connection.CloudConnectionService._build_verification_adapter",
        return_value=mock_adapter,
    ):
        with pytest.raises(AdapterError) as exc_info:
            await service.verify_connection("aws", connection.id, tenant_id)

        error = exc_info.value
        error_str = str(error)

        # AdapterError returns 502, not 500
        assert error.status_code == 502

        # Sensitive data MUST be absent
        assert "123456789012" not in error_str  # AWS account ID
        assert "ABC12345" not in error_str  # Secret key value
        assert "SecretKey=" not in error_str or "[REDACTED]" in error_str

        # The sanitizer replaces AccessDenied with a user-friendly message
        assert "Permission denied" in error.message or "IAM role" in error.message


@pytest.mark.asyncio
async def test_verify_connection_sanitizes_throttling_errors():
    """
    Finding #2: Verify throttling errors are sanitized to user-friendly messages.
    """
    mock_db = AsyncMock()
    service = CloudConnectionService(mock_db)
    tenant_id = uuid4()

    connection = MagicMock()
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.status = "pending"

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.side_effect = Exception(
        "Throttling: Rate exceeded for operation DescribeInstances"
    )

    with patch(
        "app.shared.core.cloud_connection.CloudConnectionService._build_verification_adapter",
        return_value=mock_adapter,
    ):
        with pytest.raises(AdapterError) as exc_info:
            await service.verify_connection("aws", connection.id, tenant_id)

        assert exc_info.value.status_code == 502
        assert "rate limit" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_verify_connection_updates_status_on_error():
    """
    Finding #2: Verify that connection status is updated to 'error' on failure.
    """
    mock_db = AsyncMock()
    service = CloudConnectionService(mock_db)
    tenant_id = uuid4()

    connection = MagicMock()
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.status = "pending"
    connection.is_active = True

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.side_effect = Exception("Some cloud error")

    with patch(
        "app.shared.core.cloud_connection.CloudConnectionService._build_verification_adapter",
        return_value=mock_adapter,
    ):
        with pytest.raises(AdapterError):
            await service.verify_connection("aws", connection.id, tenant_id)

        assert connection.status == "error"
        assert connection.is_active is False
        assert mock_db.commit.called
