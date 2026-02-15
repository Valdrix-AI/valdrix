"""
Tests for AdapterFactory
"""

import pytest
from unittest.mock import MagicMock, patch
from app.shared.adapters.factory import AdapterFactory
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.adapters.azure import AzureAdapter
from app.shared.adapters.gcp import GCPAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.hybrid import HybridAdapter


def test_get_adapter_aws_multitenant():
    """Test factory returns MultiTenantAWSAdapter for AWS connection."""
    mock_conn = MagicMock()
    mock_conn.cur_bucket_name = None
    mock_conn.cur_status = None

    with patch(
        "app.shared.adapters.factory.isinstance",
        side_effect=lambda x, t: t.__name__ == "AWSConnection",
    ):
        with patch.object(AdapterFactory, "get_adapter") as mock_method:
            mock_method.return_value = MagicMock(spec=MultiTenantAWSAdapter)
            adapter = AdapterFactory.get_adapter(mock_conn)
            assert adapter is not None


def test_get_adapter_aws_cur():
    """Test factory returns CURAdapter when CUR is configured."""
    from app.models.aws_connection import AWSConnection

    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.cur_bucket_name = "my-cur-bucket"
    mock_conn.cur_status = "active"

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AWSCURAdapter)


def test_get_adapter_azure():
    """Test factory returns AzureAdapter for Azure connection."""
    from app.models.azure_connection import AzureConnection

    mock_conn = MagicMock(spec=AzureConnection)
    mock_conn.tenant_id = "tenant-123"
    mock_conn.subscription_id = "sub-456"
    mock_conn.client_id = "client-id"
    mock_conn.client_secret = "secret"

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AzureAdapter)


def test_get_adapter_gcp():
    """Test factory returns GCPAdapter for GCP connection."""
    from app.models.gcp_connection import GCPConnection

    mock_conn = MagicMock(spec=GCPConnection)
    mock_conn.project_id = "my-project"
    mock_conn.service_account_json = "{}"

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, GCPAdapter)


def test_get_adapter_by_provider_attribute():
    """Test factory uses provider attribute for generic objects."""
    mock_conn = MagicMock()
    mock_conn.provider = "azure"

    # Remove spec so isinstance checks fail
    del mock_conn.__class__

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AzureAdapter)


def test_get_adapter_unsupported():
    """Test factory raises for unsupported type."""
    mock_conn = MagicMock()
    mock_conn.provider = "unsupported"

    with pytest.raises(ValueError, match="Unsupported connection type"):
        AdapterFactory.get_adapter(mock_conn)


def test_get_adapter_saas_provider():
    """Factory should route SaaS providers to Cloud+ SaaS adapter."""
    mock_conn = MagicMock()
    mock_conn.provider = "saas"
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, SaaSAdapter)


def test_get_adapter_license_provider():
    """Factory should route license providers to Cloud+ license adapter."""
    mock_conn = MagicMock()
    mock_conn.provider = "license"
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, LicenseAdapter)


def test_get_adapter_platform_provider():
    """Factory should route platform providers to Cloud+ platform adapter."""
    mock_conn = MagicMock()
    mock_conn.provider = "platform"
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, PlatformAdapter)


def test_get_adapter_hybrid_provider():
    """Factory should route hybrid providers to Cloud+ hybrid adapter."""
    mock_conn = MagicMock()
    mock_conn.provider = "hybrid"
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, HybridAdapter)
