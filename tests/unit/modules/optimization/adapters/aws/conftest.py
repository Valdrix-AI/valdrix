
import sys
from importlib.util import find_spec
from unittest.mock import MagicMock
import pytest

# Global mock for boto3/aiobotocore to prevent ImportErrors in CI/Test
mock_modules = [
    "boto3",
    "aioboto3",
    "botocore", 
    "botocore.exceptions",
    "botocore.session",
    "botocore.config",
]


def _module_available(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


for mod in mock_modules:
    if mod not in sys.modules:
        if _module_available(mod):
            continue
        sys.modules[mod] = MagicMock()


@pytest.fixture
def mock_aws_creds() -> dict[str, str]:
    return {
        "aws_access_key_id": "test-access-key",
        "aws_secret_access_key": "test-secret-key",
        "aws_session_token": "test-session-token",
    }
