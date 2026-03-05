import pytest
from typing import Dict
import asyncio
from typing import List, Any
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.plugin import ZombiePlugin


class FatalPluginFailure(BaseException):
    pass


class MockDetector(BaseZombieDetector):
    @property
    def provider_name(self) -> str:
        return "mock"

    def _initialize_plugins(self):
        pass

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        # Simulate work or error
        if hasattr(plugin, "should_fatal") and plugin.should_fatal:
            raise FatalPluginFailure("Fatal mock failure")
        if hasattr(plugin, "should_fail") and plugin.should_fail:
            raise RuntimeError("Mock failure")
        if hasattr(plugin, "should_timeout") and plugin.should_timeout:
            await asyncio.sleep(1)  # Sleep longer than quick timeout
        return [{"id": "zombie-1"}]


class MockPlugin(ZombiePlugin):
    def __init__(
        self,
        key: str,
        should_fail: bool = False,
        should_timeout: bool = False,
        should_fatal: bool = False,
    ):
        self._key = key
        self.should_fail = should_fail
        self.should_timeout = should_timeout
        self.should_fatal = should_fatal

    @property
    def category_key(self) -> str:
        return self._key

    async def scan(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return []


@pytest.mark.asyncio
async def test_base_detector_scan_success():
    detector = MockDetector()
    detector.plugins = [MockPlugin("test_plugin")]

    results = await detector.scan_all()

    assert results["provider"] == "mock"
    assert "test_plugin" in results
    assert len(results["test_plugin"]) == 1
    assert results["test_plugin"][0]["id"] == "zombie-1"
    assert results.get("error") is None


@pytest.mark.asyncio
async def test_base_detector_plugin_failure():
    detector = MockDetector()
    detector.plugins = [MockPlugin("fail_plugin", should_fail=True)]

    results = await detector.scan_all()

    assert results["provider"] == "mock"
    assert "fail_plugin" in results
    assert len(results["fail_plugin"]) == 0
    # Base detector logs error but continues, returning empty list for failed plugin
    # It might set a top level error if the aggregation fails, but per logic it sets result["error"] only on catastrophe?
    # Checking logic: "except Exception: logger.error... results['error'] = str(e)" is at top level
    # Individual plugin failure is caught in _run_plugin_with_timeout and returns empty list.


@pytest.mark.asyncio
async def test_base_detector_aggregation():
    detector = MockDetector()
    detector.plugins = [MockPlugin("p1"), MockPlugin("p2")]

    results = await detector.scan_all()

    assert len(results["p1"]) == 1
    assert len(results["p2"]) == 1
    # Check total waste calculation if implemented in Mock (Mock returns items without cost, so total 0)
    assert results["total_monthly_waste"] == 0.0


@pytest.mark.asyncio
async def test_base_detector_does_not_swallow_base_exceptions():
    detector = MockDetector()
    detector.plugins = [MockPlugin("fatal_plugin", should_fatal=True)]

    with pytest.raises(FatalPluginFailure):
        await detector.scan_all()
