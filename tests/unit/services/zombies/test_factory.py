import pytest
from uuid import uuid4
from unittest.mock import MagicMock
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
        name="test-azure"
    )

@pytest.fixture
def gcp_connection():
    return GCPConnection(
        id=uuid4(),
        project_id="test-project",
        name="test-gcp"
    )

def test_get_detector_aws(aws_connection):
    detector = ZombieDetectorFactory.get_detector(aws_connection)
    assert type(detector).__name__ == "AWSZombieDetector"
    assert detector.provider_name == "aws"

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
