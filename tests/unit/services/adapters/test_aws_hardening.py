import pytest
from unittest.mock import AsyncMock, MagicMock
from botocore.exceptions import ClientError
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.core.exceptions import AdapterError
from app.models.aws_connection import AWSConnection


@pytest.mark.asyncio
async def test_adapter_wraps_sts_error():
    # Arrange
    connection = MagicMock(spec=AWSConnection)
    connection.role_arn = "arn:aws:iam::123456789012:role/TestRole"
    connection.external_id = "vx-test"

    adapter = MultiTenantAWSAdapter(connection)

    # Mock botocore ClientError
    error_response = {
        "Error": {"Code": "AccessDenied", "Message": "User is not authorized"}
    }
    client_error = ClientError(error_response, "AssumeRole")

    # Mock aioboto3 session and client
    mock_sts_client = AsyncMock()
    mock_sts_client.assume_role.side_effect = client_error

    # We need to mock the async context manager
    mock_sts_cm = MagicMock()
    mock_sts_cm.__aenter__.return_value = mock_sts_client

    adapter.session.client = MagicMock(return_value=mock_sts_cm)

    # Act & Assert
    with pytest.raises(AdapterError) as exc_info:
        await adapter.get_credentials()

    # Assert error is sanitized (AdapterError sanitizes AccessDenied messages)
    assert "Permission denied" in str(exc_info.value) or "Valdrics IAM role" in str(
        exc_info.value
    )
    assert exc_info.value.code == "AccessDenied"
    assert exc_info.value.status_code == 502
