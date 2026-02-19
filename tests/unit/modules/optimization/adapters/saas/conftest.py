
import sys
from importlib.util import find_spec
from unittest.mock import MagicMock

# Global mock for Azure SDKs to prevent ImportErrors in SaaS tests
# (caused by registry triggering Azure plugin imports)
mock_modules = [
    "azure.mgmt.cognitiveservices",
    "azure.mgmt.search",
    "azure.mgmt.monitor",
    "azure.mgmt.compute",
    "azure.mgmt.compute.aio",
    "azure.mgmt.storage",
    "azure.mgmt.network",
    "azure.mgmt.costmanagement",
    "azure.mgmt.costmanagement.aio",
    "azure.core",
    "azure.core.credentials",
    "azure.core.exceptions",
    "azure.core.pipeline",
    "azure.core.rest",
    "azure.identity",
    "azure.identity.aio" 
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
