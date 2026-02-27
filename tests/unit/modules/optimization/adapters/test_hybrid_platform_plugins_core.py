from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.optimization.adapters.hybrid.plugins import core as hybrid_core
from app.modules.optimization.adapters.platform.plugins import core as platform_core


@pytest.mark.parametrize(
    ("to_float", "to_int"),
    [
        (hybrid_core._to_float, hybrid_core._to_int),
        (platform_core._to_float, platform_core._to_int),
    ],
)
def test_plugin_core_numeric_helpers_handle_invalid_values(to_float, to_int) -> None:
    assert to_float("3.5") == 3.5
    assert to_float(None, default=9.0) == 9.0
    assert to_float("bad", default=2.0) == 2.0
    assert to_int("10") == 10
    assert to_int("bad") is None
    assert to_int(None) is None


def test_hybrid_and_platform_plugin_category_keys() -> None:
    assert hybrid_core.IdleHybridResourcesPlugin().category_key == "idle_hybrid_resources"
    assert platform_core.IdlePlatformServicesPlugin().category_key == "idle_platform_services"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin",
    [hybrid_core.IdleHybridResourcesPlugin(), platform_core.IdlePlatformServicesPlugin()],
)
async def test_plugin_core_scan_returns_empty_for_non_list_cost_feed(plugin) -> None:
    out = await plugin.scan(session=MagicMock(), region="us-east-1", cost_feed="not-a-list")
    assert out == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin",
    [hybrid_core.IdleHybridResourcesPlugin(), platform_core.IdlePlatformServicesPlugin()],
)
async def test_plugin_core_scan_skips_invalid_entries_and_non_positive_cost(plugin) -> None:
    out = await plugin.scan(
        session=MagicMock(),
        region="us-east-1",
        cost_feed=[
            "not-a-dict",
            {"service": "svc-a", "monthly_cost": 0},
            {"service": "svc-b", "monthly_cost": -10},
        ],
    )
    assert out == []


@pytest.mark.asyncio
async def test_idle_hybrid_resources_plugin_allocated_units_branch_and_fallback_id() -> None:
    plugin = hybrid_core.IdleHybridResourcesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "service": "Private Cluster",
                "monthly_cost": "200",
                "allocated_cpu": "10",
                "used_cpu": "4",
            }
        ],
    )

    assert len(out) == 1
    item = out[0]
    assert item["resource_id"] == "hybrid-private-cluster-0"
    assert item["resource_name"] == "Private Cluster"
    assert item["monthly_cost"] == 120.0
    assert "6 unused units out of 10" in item["explainability_notes"]


@pytest.mark.asyncio
async def test_idle_hybrid_resources_plugin_utilization_branch() -> None:
    plugin = hybrid_core.IdleHybridResourcesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "vendor": "VMware",
                "host_id": "host-1",
                "amount_usd": 100,
                "cpu_utilization_pct": 20,
            }
        ],
    )

    assert len(out) == 1
    assert out[0]["resource_id"] == "host-1"
    assert out[0]["monthly_cost"] == 80.0
    assert "utilization is 20.0%" in out[0]["explainability_notes"]


@pytest.mark.asyncio
async def test_idle_hybrid_resources_plugin_status_branch_and_no_waste_path() -> None:
    plugin = hybrid_core.IdleHybridResourcesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "service": "Healthy Host",
                "resource_id": "hyb-keep",
                "monthly_cost": 150,
                "status": "active",
                "utilization_pct": 60,
            },
            {
                "service": "Retired Host",
                "resource_id": "hyb-retired",
                "monthly_cost": 150,
                "status": "retired",
            },
        ],
    )

    assert len(out) == 1
    assert out[0]["resource_id"] == "hyb-retired"
    assert out[0]["monthly_cost"] == 150.0
    assert "resource status is retired" in out[0]["explainability_notes"]


@pytest.mark.asyncio
async def test_idle_platform_services_plugin_allocated_units_branch_and_service_id() -> None:
    plugin = platform_core.IdlePlatformServicesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "service": "Observability",
                "service_id": "svc-obs-1",
                "cost_usd": 120,
                "purchased_units": 20,
                "utilized_units": 5,
            }
        ],
    )

    assert len(out) == 1
    assert out[0]["resource_id"] == "svc-obs-1"
    assert out[0]["monthly_cost"] == 90.0
    assert "15 unused units out of 20" in out[0]["explainability_notes"]


@pytest.mark.asyncio
async def test_idle_platform_services_plugin_utilization_branch() -> None:
    plugin = platform_core.IdlePlatformServicesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "vendor": "Datadog",
                "resource_id": "dd-1",
                "monthly_cost": 250,
                "utilization_percent": 20,
            }
        ],
    )

    assert len(out) == 1
    assert out[0]["resource_id"] == "dd-1"
    assert out[0]["monthly_cost"] == 200.0
    assert "utilization is 20.0%" in out[0]["explainability_notes"]


@pytest.mark.asyncio
async def test_idle_platform_services_plugin_status_branch_and_no_waste_path() -> None:
    plugin = platform_core.IdlePlatformServicesPlugin()

    out = await plugin.scan(
        session=MagicMock(),
        region="ignored",
        cost_feed=[
            {
                "service": "Healthy Platform",
                "resource_id": "plat-keep",
                "monthly_cost": 180,
                "status": "enabled",
                "utilization": 50,
            },
            {
                "service": "Disabled Platform",
                "resource_id": "plat-disabled",
                "monthly_cost": 180,
                "status": "disabled",
            },
        ],
    )

    assert len(out) == 1
    assert out[0]["resource_id"] == "plat-disabled"
    assert out[0]["monthly_cost"] == 180.0
    assert "service status is disabled" in out[0]["explainability_notes"]
