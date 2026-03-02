import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.shared.core.cloud_connection import CloudConnectionService
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.mark.asyncio
async def test_list_all_connections(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)

    mock_aws = [MagicMock(spec=AWSConnection), MagicMock(spec=AWSConnection)]
    mock_azure = [MagicMock(spec=AzureConnection)]
    mock_gcp = []
    mock_saas = [MagicMock(spec=SaaSConnection)]
    mock_license = [MagicMock(spec=LicenseConnection)]
    mock_platform = [MagicMock(spec=PlatformConnection)]
    mock_hybrid = [MagicMock(spec=HybridConnection)]

    # Mock sequence of DB executions
    mock_db.execute.side_effect = [
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_aws)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_azure)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_gcp)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_saas)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_license)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_platform)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_hybrid)),
    ]

    results = await service.list_all_connections(tenant_id)

    assert results["aws"] == mock_aws
    assert results["azure"] == mock_azure
    assert results["gcp"] == mock_gcp
    assert results["saas"] == mock_saas
    assert results["license"] == mock_license
    assert results["platform"] == mock_platform
    assert results["hybrid"] == mock_hybrid
    assert mock_db.execute.call_count == 7


@pytest.mark.asyncio
async def test_verify_connection_unsupported_provider(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("unsupported", uuid4(), tenant_id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_connection_not_found(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("aws", uuid4(), tenant_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_connection_success(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    connection = MagicMock(spec=AWSConnection)
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.aws_account_id = "123456789012"
    connection.status = "pending"

    # Ensure attributes exist for hasattr checks
    connection.is_active = False
    connection.last_verified_at = None

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True

    with patch(
        "app.shared.core.cloud_connection.CloudConnectionService._build_verification_adapter",
        return_value=mock_adapter,
    ):
        result = await service.verify_connection("aws", connection.id, tenant_id)

        assert result["status"] == "active"
        assert result["provider"] == "aws"
        assert result["account_id"] == "123456789012"
        assert connection.status == "active"
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_verify_connection_failure(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)

    # Use non-spec mock to avoid hasattr issues with spec
    connection = MagicMock()
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.is_active = True
    connection.status = "pending"

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = False

    with patch(
        "app.shared.core.cloud_connection.AdapterFactory.get_adapter",
        return_value=mock_adapter,
    ):
        with pytest.raises(HTTPException) as exc:
            await service.verify_connection("azure", connection.id, tenant_id)
        assert exc.value.status_code == 400
        assert connection.is_active is False
        assert connection.status == "error"


@pytest.mark.asyncio
async def test_verify_connection_normalizes_provider_input(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    connection = MagicMock(spec=AWSConnection)
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.aws_account_id = "123456789012"
    connection.status = "pending"
    connection.is_active = False
    connection.last_verified_at = None

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True

    with patch(
        "app.shared.core.cloud_connection.CloudConnectionService._build_verification_adapter",
        return_value=mock_adapter,
    ):
        result = await service.verify_connection("AWS", connection.id, tenant_id)

    assert result["provider"] == "aws"
    assert result["account_id"] == "123456789012"


@pytest.mark.asyncio
async def test_verify_connection_cloud_plus_reference_uses_vendor(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    connection = MagicMock(spec=SaaSConnection)
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.vendor = "stripe"
    connection.name = "Stripe Billing"
    connection.is_active = False
    connection.error_message = None

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res

    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True

    with patch(
        "app.shared.core.cloud_connection.AdapterFactory.get_adapter",
        return_value=mock_adapter,
    ):
        result = await service.verify_connection("saas", connection.id, tenant_id)

    assert result["provider"] == "saas"
    assert result["account_id"] == "stripe"


def test_get_aws_setup_templates():
    result = CloudConnectionService.get_aws_setup_templates("ext-123")
    assert "ext-123" in result["magic_link"]
    assert "ext-123" in result["terraform_snippet"]


def test_get_aws_setup_templates_uses_configured_console_region():
    with patch(
        "app.shared.core.cloud_connection.get_settings",
        return_value=MagicMock(
            AWS_DEFAULT_REGION="eu-west-2",
            AWS_SUPPORTED_REGIONS=["us-east-1", "eu-west-2"],
        ),
    ):
        result = CloudConnectionService.get_aws_setup_templates("ext-123")
    assert "region=eu-west-2" in result["magic_link"]


def test_build_verification_adapter_aws_uses_multitenant_and_resolves_region():
    service = CloudConnectionService(AsyncMock())
    connection = MagicMock(spec=AWSConnection)
    connection.aws_account_id = "123456789012"
    connection.role_arn = "arn:aws:iam::123456789012:role/ValdricsRole"
    connection.external_id = "ext-123"
    connection.region = "global"
    connection.cur_bucket_name = None
    connection.cur_report_name = None
    connection.cur_prefix = None

    with patch(
        "app.shared.adapters.aws_utils.get_settings",
        return_value=MagicMock(
            AWS_SUPPORTED_REGIONS=["eu-west-1"],
            AWS_DEFAULT_REGION="eu-west-1",
        ),
    ):
        adapter = service._build_verification_adapter("aws", connection)

    assert isinstance(adapter, MultiTenantAWSAdapter)
    assert adapter.credentials.region == "eu-west-1"
