"""
Tests for AdapterFactory
"""

import pytest
from unittest.mock import MagicMock, patch
from app.shared.adapters.factory import AdapterFactory
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.adapters.azure import AzureAdapter
from app.shared.adapters.gcp import GCPAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.hybrid import HybridAdapter
from app.shared.core.exceptions import ConfigurationError


def test_get_adapter_aws_requires_cur():
    """AWS adapter selection should hard-fail when CUR is not configured."""
    from app.models.aws_connection import AWSConnection

    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.aws_account_id = "123456789012"
    mock_conn.role_arn = "arn:aws:iam::123456789012:role/ValdrixRole"
    mock_conn.external_id = "ext-123"
    mock_conn.region = "us-east-1"
    mock_conn.cur_bucket_name = None
    mock_conn.cur_status = None
    mock_conn.cur_report_name = None
    mock_conn.cur_prefix = None

    with pytest.raises(ConfigurationError, match="CUR"):
        AdapterFactory.get_adapter(mock_conn)


def test_get_adapter_aws_cur():
    """Test factory returns CURAdapter when CUR is configured."""
    from app.models.aws_connection import AWSConnection

    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.aws_account_id = "123456789012"
    mock_conn.role_arn = "arn:aws:iam::123456789012:role/ValdrixRole"
    mock_conn.external_id = "ext-123"
    mock_conn.region = "us-east-1"
    mock_conn.cur_bucket_name = "my-cur-bucket"
    mock_conn.cur_report_name = "cost-report"
    mock_conn.cur_prefix = "reports/"
    mock_conn.cur_status = "active"

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AWSCURAdapter)


def test_get_adapter_aws_cur_global_region_uses_config_default():
    """AWS region hint 'global' should resolve to configured AWS default for CUR adapter."""
    from app.models.aws_connection import AWSConnection

    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.aws_account_id = "123456789012"
    mock_conn.role_arn = "arn:aws:iam::123456789012:role/ValdrixRole"
    mock_conn.external_id = "ext-123"
    mock_conn.region = "global"
    mock_conn.cur_bucket_name = "my-cur-bucket"
    mock_conn.cur_report_name = "cost-report"
    mock_conn.cur_prefix = "reports/"
    mock_conn.cur_status = "active"

    with patch(
        "app.shared.adapters.aws_utils.get_settings",
        return_value=MagicMock(
            AWS_SUPPORTED_REGIONS=["eu-west-1"],
            AWS_DEFAULT_REGION="eu-west-1",
        ),
    ):
        adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AWSCURAdapter)
    assert adapter.credentials.region == "eu-west-1"


def test_get_adapter_azure():
    """Test factory returns AzureAdapter for Azure connection."""
    from app.models.azure_connection import AzureConnection

    mock_conn = MagicMock(spec=AzureConnection)
    mock_conn.azure_tenant_id = "tenant-123"
    mock_conn.subscription_id = "sub-456"
    mock_conn.client_id = "client-id"
    mock_conn.client_secret = "secret"
    mock_conn.auth_method = "client_secret"

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, AzureAdapter)


def test_get_adapter_gcp():
    """Test factory returns GCPAdapter for GCP connection."""
    from app.models.gcp_connection import GCPConnection

    mock_conn = MagicMock(spec=GCPConnection)
    mock_conn.project_id = "my-project"
    mock_conn.service_account_json = "{}"
    mock_conn.auth_method = "service_account"
    mock_conn.billing_project_id = None
    mock_conn.billing_dataset = None
    mock_conn.billing_table = None

    adapter = AdapterFactory.get_adapter(mock_conn)

    assert isinstance(adapter, GCPAdapter)


def test_get_adapter_unsupported():
    """Test factory raises for unsupported type."""
    mock_conn = MagicMock()
    mock_conn.provider = "unsupported"

    with pytest.raises(ConfigurationError, match="Unsupported connection type"):
        AdapterFactory.get_adapter(mock_conn)


def test_get_adapter_saas_provider():
    """Factory should route SaaS providers to Cloud+ SaaS adapter."""
    from app.models.saas_connection import SaaSConnection

    mock_conn = MagicMock(spec=SaaSConnection)
    mock_conn.vendor = "stripe"
    mock_conn.auth_method = "api_key"
    mock_conn.api_key = "sk_test_123"
    mock_conn.connector_config = {"region": "us"}
    mock_conn.spend_feed = []
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, SaaSAdapter)


def test_get_adapter_license_provider():
    """Factory should route license providers to Cloud+ license adapter."""
    from app.models.license_connection import LicenseConnection

    mock_conn = MagicMock(spec=LicenseConnection)
    mock_conn.vendor = "microsoft_365"
    mock_conn.auth_method = "api_key"
    mock_conn.api_key = "token-123"
    mock_conn.connector_config = {}
    mock_conn.license_feed = []
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, LicenseAdapter)


def test_get_adapter_platform_provider():
    """Factory should route platform providers to Cloud+ platform adapter."""
    from app.models.platform_connection import PlatformConnection

    mock_conn = MagicMock(spec=PlatformConnection)
    mock_conn.vendor = "datadog"
    mock_conn.auth_method = "api_key"
    mock_conn.api_key = "dd-key"
    mock_conn.api_secret = "dd-secret"
    mock_conn.connector_config = {}
    mock_conn.spend_feed = []
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, PlatformAdapter)


def test_get_adapter_hybrid_provider():
    """Factory should route hybrid providers to Cloud+ hybrid adapter."""
    from app.models.hybrid_connection import HybridConnection

    mock_conn = MagicMock(spec=HybridConnection)
    mock_conn.vendor = "kubernetes"
    mock_conn.auth_method = "api_key"
    mock_conn.api_key = "k8s-key"
    mock_conn.api_secret = "k8s-secret"
    mock_conn.connector_config = {}
    mock_conn.spend_feed = []
    adapter = AdapterFactory.get_adapter(mock_conn)
    assert isinstance(adapter, HybridAdapter)
