import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection


@pytest.fixture
def aws_connection():
    return AWSConnection(id=uuid4(), region="us-east-1")


@pytest.fixture
def azure_connection():
    return AzureConnection(
        id=uuid4(),
        azure_tenant_id="tenant-id",
        client_id="client-id",
        client_secret="secret",
        subscription_id="sub-id",
        name="test-azure",
    )


@pytest.fixture
def gcp_connection():
    return GCPConnection(id=uuid4(), project_id="test-project", name="test-gcp")


def test_get_detector_aws(aws_connection):
    detector = ZombieDetectorFactory.get_detector(aws_connection)
    assert type(detector).__name__ == "AWSZombieDetector"
    assert detector.provider_name == "aws"


def test_get_detector_aws_global_region_hint_uses_connection_region():
    conn = SimpleNamespace(provider="aws", region="eu-west-1")
    detector = ZombieDetectorFactory.get_detector(conn, region="global")
    assert type(detector).__name__ == "AWSZombieDetector"
    assert detector.region == "eu-west-1"


def test_get_detector_aws_global_region_hint_falls_back_to_config_default():
    conn = SimpleNamespace(provider="aws", region="")
    with patch(
        "app.shared.core.connection_state.get_settings",
        return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-central-1"),
    ):
        detector = ZombieDetectorFactory.get_detector(conn, region="global")
    assert type(detector).__name__ == "AWSZombieDetector"
    assert detector.region == "eu-central-1"


def test_get_detector_azure(azure_connection):
    detector = ZombieDetectorFactory.get_detector(azure_connection)
    assert type(detector).__name__ == "AzureZombieDetector"
    assert detector.provider_name == "azure"


def test_get_detector_gcp(gcp_connection):
    detector = ZombieDetectorFactory.get_detector(gcp_connection)
    assert type(detector).__name__ == "GCPZombieDetector"
    assert detector.provider_name == "gcp"


def test_get_detector_unknown_type():
    with pytest.raises(ValueError, match="Unsupported connection type"):
        ZombieDetectorFactory.get_detector(object())


def test_get_detector_saas_provider_attr():
    conn = MagicMock()
    conn.provider = "saas"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "SaaSZombieDetector"
    assert detector.provider_name == "saas"


def test_get_detector_license_provider_attr():
    conn = MagicMock()
    conn.provider = "license"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "LicenseZombieDetector"
    assert detector.provider_name == "license"


def test_get_detector_platform_provider_attr():
    conn = MagicMock()
    conn.provider = "platform"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "PlatformZombieDetector"
    assert detector.provider_name == "platform"


def test_get_detector_hybrid_provider_attr():
    conn = MagicMock()
    conn.provider = "hybrid"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "HybridZombieDetector"
    assert detector.provider_name == "hybrid"


def test_get_detector_azure_provider_attr_without_class_name():
    conn = MagicMock()
    conn.provider = "azure"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "AzureZombieDetector"
    assert detector.provider_name == "azure"


def test_get_detector_gcp_provider_attr_without_class_name():
    conn = MagicMock()
    conn.provider = "gcp"
    detector = ZombieDetectorFactory.get_detector(conn)
    assert type(detector).__name__ == "GCPZombieDetector"
    assert detector.provider_name == "gcp"
