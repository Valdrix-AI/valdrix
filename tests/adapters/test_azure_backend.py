import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.shared.connections.azure import AzureConnectionService
from app.models.azure_connection import AzureConnection

@pytest.mark.asyncio
async def test_azure_verify_connection_success():
    # Arrange
    db = AsyncMock()
    tenant_id = uuid4()
    connection_id = uuid4()
    mock_connection = MagicMock(spec=AzureConnection)
    mock_connection.id = connection_id
    mock_connection.tenant_id = tenant_id
    mock_connection.is_active = False

    # Setup the mock result to return a regular MagicMock, not an AsyncMock
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_connection
    db.execute.return_value = result_mock

    with patch("app.shared.connections.azure.AzureAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=True)

        # Act
        response = await AzureConnectionService(db).verify_connection(connection_id, tenant_id)

        # Assert
        assert response["status"] == "active"
        assert mock_connection.is_active is True
        db.commit.assert_called()

@pytest.mark.asyncio
async def test_azure_verify_connection_failure():
    # Arrange
    db = AsyncMock()
    tenant_id = uuid4()
    connection_id = uuid4()
    mock_connection = MagicMock(spec=AzureConnection)
    mock_connection.id = connection_id
    mock_connection.tenant_id = tenant_id
    mock_connection.is_active = False

    # Setup the mock result to return a regular MagicMock, not an AsyncMock
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_connection
    db.execute.return_value = result_mock

    with patch("app.shared.connections.azure.AzureAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=False)

        # Act & Assert
        with pytest.raises(HTTPException) as exc:
            await AzureConnectionService(db).verify_connection(connection_id, tenant_id)
        
        assert exc.value.status_code == 400
        assert mock_connection.is_active is False
        db.commit.assert_called()
