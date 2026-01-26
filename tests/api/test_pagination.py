
import pytest
from app.modules.optimization.domain.detector import ZombieDetector

class AsyncContextManagerMock:
    def __init__(self, return_value):
        self.return_value = return_value
    async def __aenter__(self):
        return self.return_value
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class AsyncIterator:
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)

# NOTE: The following tests were removed because they reference methods
# (_find_underused_nat_gateways, _find_legacy_ecr_images) that were
# refactored into the plugin architecture (see app/services/zombies/plugins/).
# New tests should target the plugin classes directly or the scan_all() method.

@pytest.mark.asyncio
async def test_zombie_detector_instantiation():
    """Verify that ZombieDetector can be instantiated."""
    detector = ZombieDetector(region="us-east-1")
    assert detector.region == "us-east-1"
    assert len(detector.plugins) > 0  # Should have plugins loaded

