import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.api.v1.connections import verify_aws_connection

@pytest.mark.asyncio
async def test_verify_aws_connection_success():
    """Verify that verify_aws_connection returns True on success."""
    
    # Mock mocks
    mock_sts = AsyncMock()
    # verify_aws_connection calls assume_role
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "foo",
            "SecretAccessKey": "bar",
            "SessionToken": "baz",
            "Expiration": "2026-01-01"
        }
    }
    
    # Mock Context Manager
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_sts
    mock_cm.__aexit__.return_value = None
    
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.client.return_value = mock_cm
        
        success, error = await verify_aws_connection("arn:aws:iam::123:role/TestRole", "external-id-123")
        
        assert success is True
        assert error is None
        mock_sts.assume_role.assert_called_once()

@pytest.mark.asyncio
async def test_verify_aws_connection_failure():
    """Verify that verify_aws_connection returns False on failure."""
    from botocore.exceptions import ClientError
    
    mock_sts = AsyncMock()
    mock_sts.assume_role.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "assume_role"
    )
    
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_sts
    mock_cm.__aexit__.return_value = None
    
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.client.return_value = mock_cm
        
        success, error = await verify_aws_connection("arn:aws:iam::123:role/TestRole", "external-id-123")
        
        assert success is False
        assert error is not None
        assert "AccessDenied" in error
