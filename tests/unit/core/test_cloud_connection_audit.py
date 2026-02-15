import pytest
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException
from app.shared.core.cloud_connection import CloudConnectionService
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return CloudConnectionService(mock_db)


@pytest.mark.asyncio
async def test_list_all_connections(service, mock_db):
    tenant_id = uuid4()

    # Mock results for AWS, Azure, GCP, SaaS, License queries
    mock_aws = [AWSConnection(id=uuid4(), tenant_id=tenant_id, aws_account_id="123")]
    mock_azure = [
        AzureConnection(id=uuid4(), tenant_id=tenant_id, subscription_id="sub-1")
    ]
    mock_gcp = [GCPConnection(id=uuid4(), tenant_id=tenant_id, project_id="proj-1")]
    mock_saas = [
        SaaSConnection(
            id=uuid4(),
            tenant_id=tenant_id,
            name="Salesforce",
            vendor="salesforce",
            auth_method="manual",
            spend_feed=[],
        )
    ]
    mock_license = [
        LicenseConnection(
            id=uuid4(),
            tenant_id=tenant_id,
            name="M365",
            vendor="microsoft",
            auth_method="manual",
            license_feed=[],
        )
    ]

    # Map side effects to consecutive execute calls
    mock_res_aws = MagicMock()
    mock_res_aws.scalars.return_value.all.return_value = mock_aws

    mock_res_azure = MagicMock()
    mock_res_azure.scalars.return_value.all.return_value = mock_azure

    mock_res_gcp = MagicMock()
    mock_res_gcp.scalars.return_value.all.return_value = mock_gcp

    mock_res_saas = MagicMock()
    mock_res_saas.scalars.return_value.all.return_value = mock_saas

    mock_res_license = MagicMock()
    mock_res_license.scalars.return_value.all.return_value = mock_license

    mock_db.execute.side_effect = [
        mock_res_aws,
        mock_res_azure,
        mock_res_gcp,
        mock_res_saas,
        mock_res_license,
    ]

    connections = await service.list_all_connections(tenant_id)

    assert len(connections["aws"]) == 1
    assert len(connections["azure"]) == 1
    assert len(connections["gcp"]) == 1
    assert len(connections["saas"]) == 1
    assert len(connections["license"]) == 1
    assert connections["aws"][0].aws_account_id == "123"


@pytest.mark.asyncio
async def test_verify_connection_success_aws(service, mock_db):
    tenant_id = uuid4()
    conn_id = uuid4()

    connection = AWSConnection(
        id=conn_id, tenant_id=tenant_id, aws_account_id="123", status="pending"
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter",
        return_value=mock_adapter,
    ):
        with patch("app.shared.core.cloud_connection.audit_log") as mock_audit:
            result = await service.verify_connection("aws", conn_id, tenant_id)

            assert result["status"] == "active"
            assert result["account_id"] == "123"
            assert connection.status == "active"
            assert connection.last_verified_at is not None
            mock_db.commit.assert_awaited_once()
            mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_verify_connection_failed_azure(service, mock_db):
    tenant_id = uuid4()
    conn_id = uuid4()

    # AzureConnection uses is_active, not status
    connection = AzureConnection(
        id=conn_id, tenant_id=tenant_id, subscription_id="sub-1", is_active=False
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = False

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter",
        return_value=mock_adapter,
    ):
        with pytest.raises(HTTPException) as exc:
            await service.verify_connection("azure", conn_id, tenant_id)

        assert exc.value.status_code == 400
        assert connection.is_active is False
        mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_connection_not_found(service, mock_db):
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("aws", uuid4(), uuid4())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_connection_unsupported_provider(service):
    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("unsupported", uuid4(), uuid4())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_connection_internal_error(service, mock_db):
    tenant_id = uuid4()
    conn_id = uuid4()
    connection = AWSConnection(id=conn_id, tenant_id=tenant_id, status="pending")

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    with patch(
        "app.shared.adapters.factory.AdapterFactory.get_adapter",
        side_effect=Exception("API Error"),
    ):
        with pytest.raises(HTTPException) as exc:
            await service.verify_connection("aws", conn_id, tenant_id)

        assert exc.value.status_code == 500
        assert connection.status == "error"
        assert connection.error_message == "API Error"


def test_get_aws_setup_templates():
    templates = CloudConnectionService.get_aws_setup_templates("ext-123")
    assert "magic_link" in templates
    assert "ext-123" in templates["magic_link"]
    assert "terraform_snippet" in templates
