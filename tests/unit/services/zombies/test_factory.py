import pytest
from uuid import uuid4
from app.services.zombies.factory import ZombieDetectorFactory
from app.services.zombies.aws.detector import AWSZombieDetector
from app.services.zombies.az_provider.detector import AzureZombieDetector
from app.services.zombies.gcp_provider.detector import GCPZombieDetector
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection

@pytest.fixture
def aws_connection():
    return AWSConnection(id=uuid4(), region="us-east-1")

@pytest.fixture
def azure_connection():
    return AzureConnection(id=uuid4())

@pytest.fixture
def gcp_connection():
    return GCPConnection(id=uuid4())

def test_get_detector_aws(aws_connection):
    detector = ZombieDetectorFactory.get_detector(aws_connection)
    assert isinstance(detector, AWSZombieDetector)
    assert detector.provider_name == "aws"

def test_get_detector_azure(azure_connection):
    detector = ZombieDetectorFactory.get_detector(azure_connection)
    assert isinstance(detector, AzureZombieDetector)
    assert detector.provider_name == "azure"

def test_get_detector_gcp(gcp_connection):
    detector = ZombieDetectorFactory.get_detector(gcp_connection)
    assert isinstance(detector, GCPZombieDetector)
    assert detector.provider_name == "gcp"

def test_get_detector_unknown_type():
    with pytest.raises(ValueError, match="Unsupported connection type"):
        ZombieDetectorFactory.get_detector(object())
