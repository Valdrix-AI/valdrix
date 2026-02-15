import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.optimization.domain.aws_provider.detector import AWSZombieDetector
from app.modules.optimization.domain.aws_provider.plugins import UnattachedVolumesPlugin


@pytest.fixture
def mock_boto_session():
    with patch("aioboto3.Session") as mock:
        yield mock


@pytest.fixture
def detector(mock_boto_session):
    return AWSZombieDetector(
        region="us-west-2",
        credentials={
            "AccessKeyId": "test",
            "SecretAccessKey": "test",
            "SessionToken": "test",
        },
    )


def test_initialization(detector):
    assert detector.region == "us-west-2"
    assert detector.provider_name == "aws"
    assert detector.credentials == {
        "AccessKeyId": "test",
        "SecretAccessKey": "test",
        "SessionToken": "test",
    }


def test_plugin_registration(detector):
    detector._initialize_plugins()
    assert len(detector.plugins) > 0
    assert any(isinstance(p, UnattachedVolumesPlugin) for p in detector.plugins)


@pytest.mark.asyncio
async def test_execute_plugin_scan(detector):
    # Mock a plugin
    mock_plugin = AsyncMock()
    mock_plugin.scan.return_value = [{"id": "vol-123"}]

    # Mock the session (not actually used by the mock plugin but passed)
    detector.session = MagicMock()

    results = await detector._execute_plugin_scan(mock_plugin)

    assert results == [{"id": "vol-123"}]
    mock_plugin.scan.assert_called_once()
    kwargs = mock_plugin.scan.call_args.kwargs
    assert kwargs["session"] == detector.session
    assert kwargs["region"] == "us-west-2"
    assert kwargs["credentials"] == detector.credentials
