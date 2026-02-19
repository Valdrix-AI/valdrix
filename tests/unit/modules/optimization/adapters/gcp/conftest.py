
import sys
from importlib.util import find_spec
from unittest.mock import MagicMock
import pytest

# Global mock for GCP SDKs to prevent ImportErrors in CI/Test
mock_modules = [
    "google.cloud",
    "google.cloud.compute_v1",
    "google.cloud.resourcemanager_v3",
    "google.cloud.aiplatform",
    "google.cloud.monitoring_v3",
    "google.oauth2",
    "google.oauth2.service_account",
    "google.api_core",
    "google.api_core.exceptions",
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
def mock_gcp_creds() -> MagicMock:
    return MagicMock(name="gcp_credentials")
