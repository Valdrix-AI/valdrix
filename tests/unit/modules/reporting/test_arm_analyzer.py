from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.reporting.domain.arm_analyzer import ArmMigrationAnalyzer
from app.shared.core.exceptions import ExternalAPIError


class _Analyzer(ArmMigrationAnalyzer):
    def is_arm(self, instance_type: str) -> bool:
        return instance_type.startswith("m7g")

    def get_equivalent(self, instance_type: str) -> tuple[str, int] | None:
        if instance_type.startswith("m5"):
            return ("m7g.large", 30)
        return None

    def get_instance_type_from_resource(self, resource: dict[str, object]) -> str | None:
        value = resource.get("instance_type")
        return str(value) if isinstance(value, str) else None


@pytest.mark.asyncio
async def test_arm_analyze_handles_recoverable_discovery_errors() -> None:
    adapter = MagicMock()
    adapter.provider = "aws"
    adapter.discover_resources = AsyncMock(
        side_effect=ExternalAPIError("adapter unavailable")
    )
    analyzer = _Analyzer(adapter=adapter, region="us-east-1")

    out = await analyzer.analyze()

    assert out["total_instances"] == 0
    assert out["migration_candidates"] == 0
    assert "adapter unavailable" in out["error"]


@pytest.mark.asyncio
async def test_arm_analyze_does_not_swallow_base_exceptions() -> None:
    adapter = MagicMock()
    adapter.provider = "aws"
    adapter.discover_resources = AsyncMock(side_effect=KeyboardInterrupt("stop"))
    analyzer = _Analyzer(adapter=adapter, region="us-east-1")

    with pytest.raises(KeyboardInterrupt, match="stop"):
        await analyzer.analyze()

