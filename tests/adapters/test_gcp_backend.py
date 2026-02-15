import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.shared.connections.gcp import GCPConnectionService
from app.models.gcp_connection import GCPConnection


@pytest.mark.asyncio
async def test_gcp_verify_sa_success():
    # Arrange
    db = AsyncMock()
    tenant_id = uuid4()
    connection_id = uuid4()
    mock_connection = MagicMock(spec=GCPConnection)
    mock_connection.id = connection_id
    mock_connection.tenant_id = tenant_id
    mock_connection.auth_method = "secret"
    mock_connection.is_active = False

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_connection
    db.execute.return_value = result_mock

    with patch("app.shared.connections.gcp.GCPAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=True)

        # Act
        response = await GCPConnectionService(db).verify_connection(
            connection_id, tenant_id
        )

        # Assert - production returns 'success', not 'active'
        assert response["status"] == "success"
        assert mock_connection.is_active is True
        db.commit.assert_called()


@pytest.mark.asyncio
async def test_gcp_verify_oidc_success():
    # Arrange - OIDC/Workload Identity connections also use GCPAdapter
    db = AsyncMock()
    tenant_id = uuid4()
    connection_id = uuid4()
    mock_connection = MagicMock(spec=GCPConnection)
    mock_connection.id = connection_id
    mock_connection.tenant_id = tenant_id
    mock_connection.auth_method = "workload_identity"
    mock_connection.is_active = False

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_connection
    db.execute.return_value = result_mock

    # Production uses GCPAdapter for all auth methods
    with patch("app.shared.connections.gcp.GCPAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=True)

        # Act
        response = await GCPConnectionService(db).verify_connection(
            connection_id, tenant_id
        )

        # Assert - production returns 'success', not 'active'
        assert response["status"] == "success"
        assert mock_connection.is_active is True
        db.commit.assert_called()
