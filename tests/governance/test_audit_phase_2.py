import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.shared.llm.factory import LLMFactory


@pytest.mark.asyncio
async def test_zombie_detector_factory_pass_through() -> None:
    """Verify that ZombieDetectorFactory passes the connection object to the detector."""

    # Use a subclass to ensure __name__ matches expectation
    class AWSConnectionMock(MagicMock):
        pass

    mock_connection = AWSConnectionMock()

    with patch(
        "app.modules.optimization.domain.aws_provider.detector.AWSZombieDetector.__init__",
        return_value=None,
    ) as mock_init:
        # We don't actually want to init it, just check if it's called with connection
        ZombieDetectorFactory.get_detector(mock_connection)
        mock_init.assert_called_once()
        args, kwargs = mock_init.call_args
        assert kwargs.get("connection") == mock_connection


def test_llm_factory_key_validation() -> None:
    """Verify LLM key validation for placeholders and length."""
    # Test valid key
    LLMFactory.validate_api_key("openai", "sk-proj-valid-key-that-is-long-enough-12345")

    # Test placeholder
    with pytest.raises(ValueError, match="contains a placeholder"):
        LLMFactory.validate_api_key("openai", "sk-xxx-12345")

    # Test too short
    with pytest.raises(ValueError, match="too short"):
        LLMFactory.validate_api_key("openai", "short-key")

    # Test missing
    with pytest.raises(ValueError, match="not configured"):
        LLMFactory.validate_api_key("openai", None)


def test_rate_limiter_hash_usage() -> None:
    """Verify that rate limiter uses hashed tokens to prevent bypass."""
    from app.shared.core.rate_limit import context_aware_key

    mock_request = MagicMock()
    mock_request.headers = {"Authorization": "Bearer some-token"}
    mock_request.state.tenant_id = None  # Force token logic

    # If a token is present, the key should contain a hash
    key = context_aware_key(mock_request)
    assert len(key.split(":")) >= 2
    token_part = key.split(":")[-1]
    # It should be a hash, not the literal token
    assert token_part != "some-token"
    assert len(token_part) == 16  # SHA256 truncated to 16 in code


@pytest.mark.asyncio
async def test_aws_detector_boto_config_injection() -> None:
    """Verify that AWSZombieDetector injects botocore.Config with timeouts."""
    from app.modules.optimization.domain.aws_provider.detector import AWSZombieDetector
    from botocore.config import Config

    detector = AWSZombieDetector(region="us-east-1")
    mock_plugin = MagicMock()
    mock_plugin.scan = AsyncMock(return_value=[])

    await detector._execute_plugin_scan(mock_plugin)

    mock_plugin.scan.assert_called_once()
    args, kwargs = mock_plugin.scan.call_args
    assert "config" in kwargs
    config = kwargs["config"]
    assert isinstance(config, Config)
    assert getattr(config, "connect_timeout", None) == 30  # type: ignore[attr-defined]
