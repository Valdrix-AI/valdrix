from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.domain.service import ZombieService
from app.shared.core.pricing import PricingTier


def _result_with_rows(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_scan_for_tenant_includes_platform_and_hybrid_connections() -> None:
    db = AsyncMock()
    service = ZombieService(db)
    tenant_id = uuid4()

    platform_conn = MagicMock()
    platform_conn.id = uuid4()
    platform_conn.name = "Shared Platform"
    platform_conn.provider = "platform"
    platform_conn.tenant_id = tenant_id

    hybrid_conn = MagicMock()
    hybrid_conn.id = uuid4()
    hybrid_conn.name = "Private OpenStack"
    hybrid_conn.provider = "hybrid"
    hybrid_conn.tenant_id = tenant_id

    empty = _result_with_rows([])
    platform_result = _result_with_rows([platform_conn])
    hybrid_result = _result_with_rows([hybrid_conn])

    async def execute_side_effect(stmt: object) -> MagicMock:
        query = str(stmt).lower()
        if "platform_connections" in query:
            return platform_result
        if "hybrid_connections" in query:
            return hybrid_result
        return empty

    db.execute = AsyncMock(side_effect=execute_side_effect)

    platform_detector = MagicMock()
    platform_detector.provider_name = "platform"
    platform_detector.scan_all = AsyncMock(
        return_value={
            "idle_platform_services": [
                {"resource_id": "platform-gw", "monthly_waste": 14.0}
            ]
        }
    )
    hybrid_detector = MagicMock()
    hybrid_detector.provider_name = "hybrid"
    hybrid_detector.scan_all = AsyncMock(
        return_value={
            "idle_hybrid_resources": [
                {"resource_id": "hybrid-vm-1", "monthly_waste": 26.0}
            ]
        }
    )

    def detector_side_effect(conn: object, **_: object) -> object:
        provider = str(getattr(conn, "provider", "")).lower()
        if provider == "platform":
            return platform_detector
        if provider == "hybrid":
            return hybrid_detector
        raise AssertionError(f"Unexpected provider detector request: {provider}")

    with (
        patch(
            "app.modules.optimization.domain.service.ZombieDetectorFactory.get_detector",
            side_effect=detector_side_effect,
        ),
        patch(
            "app.shared.core.pricing.get_tenant_tier",
            AsyncMock(return_value=PricingTier.FREE),
        ),
        patch("app.shared.core.ops_metrics.SCAN_LATENCY"),
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_zombies",
            AsyncMock(),
        ),
    ):
        result = await service.scan_for_tenant(tenant_id)

    assert result["scanned_connections"] == 2
    assert result["total_monthly_waste"] == 40.0
    assert len(result["idle_platform_services"]) == 1
    assert len(result["idle_hybrid_resources"]) == 1
    assert result["idle_platform_services"][0]["provider"] == "platform"
    assert result["idle_hybrid_resources"][0]["provider"] == "hybrid"


@pytest.mark.asyncio
async def test_load_connections_for_model_handles_execute_errors() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db unavailable"))
    service = ZombieService(db)

    rows = await service._load_connections_for_model(MagicMock(), uuid4())

    assert rows == []
