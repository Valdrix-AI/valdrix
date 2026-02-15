import pytest

from app.modules.optimization.adapters.license.plugins.core import (
    UnusedLicenseSeatsPlugin,
    _to_float as license_to_float,
    _to_int as license_to_int,
)
from app.modules.optimization.adapters.saas.plugins.core import (
    IdleSaaSSubscriptionsPlugin,
    _to_float as saas_to_float,
    _to_int as saas_to_int,
)
from app.modules.optimization.domain.registry import registry


def test_helpers_parse_numeric_values() -> None:
    assert license_to_float("1.25") == 1.25
    assert license_to_float(None, default=9.0) == 9.0
    assert license_to_float("bad", default=2.0) == 2.0

    assert license_to_int("10") == 10
    assert license_to_int("bad") is None
    assert license_to_int(None) is None

    assert saas_to_float("3") == 3.0
    assert saas_to_int("7") == 7


def test_plugins_are_registered_in_registry() -> None:
    assert any(
        isinstance(plugin, UnusedLicenseSeatsPlugin)
        for plugin in registry.get_plugins_for_provider("license")
    )
    assert any(
        isinstance(plugin, IdleSaaSSubscriptionsPlugin)
        for plugin in registry.get_plugins_for_provider("saas")
    )


@pytest.mark.asyncio
async def test_license_plugin_scan_handles_invalid_inputs() -> None:
    plugin = UnusedLicenseSeatsPlugin()
    assert plugin.category_key == "unused_license_seats"

    assert await plugin.scan(cost_feed="not-a-list") == []
    assert await plugin.scan(cost_feed=[None, "x", 123]) == []


@pytest.mark.asyncio
async def test_license_plugin_scan_detects_unused_seats_and_inactive_contracts() -> (
    None
):
    plugin = UnusedLicenseSeatsPlugin()
    rows = await plugin.scan(
        cost_feed=[
            # ignored: monthly cost <= 0
            {"service": "Slack", "monthly_cost": 0},
            # unused seats waste
            {
                "service": "M365",
                "monthly_cost": 100,
                "purchased_seats": 10,
                "assigned_seats": 7,
            },
            # inactive contract waste
            {"vendor": "Atlassian", "amount_usd": 40, "status": "Expired"},
            # ignored: dict but no seats mismatch + active status
            {
                "vendor": "Okta",
                "cost_usd": 25,
                "purchased_seats": 10,
                "assigned_seats": 10,
                "status": "active",
            },
        ]
    )

    assert len(rows) == 2
    assert rows[0]["resource_type"] == "License Contract"
    assert rows[0]["monthly_waste"] == 30.0  # 3/10 of 100
    assert "unused licenses" in rows[0]["explainability_notes"]

    assert rows[1]["resource_name"] == "Atlassian"
    assert rows[1]["monthly_waste"] == 40.0
    assert rows[1]["explainability_notes"] == "license status is expired"


@pytest.mark.asyncio
async def test_saas_plugin_scan_handles_invalid_inputs() -> None:
    plugin = IdleSaaSSubscriptionsPlugin()
    assert plugin.category_key == "idle_saas_subscriptions"

    assert await plugin.scan(cost_feed="not-a-list") == []
    assert await plugin.scan(cost_feed=[None, "x", 123]) == []


@pytest.mark.asyncio
async def test_saas_plugin_scan_detects_waste_from_seats_status_and_inactivity() -> (
    None
):
    plugin = IdleSaaSSubscriptionsPlugin()
    rows = await plugin.scan(
        cost_feed=[
            # unused seats waste
            {
                "vendor": "Slack",
                "monthly_cost": 50,
                "total_seats": 10,
                "active_users": 5,
            },
            # cancelled status waste
            {"service": "Datadog", "cost_usd": 30, "status": "cancelled"},
            # inactive days waste
            {"service": "Notion", "amount_usd": 12, "inactive_days": 45},
            # ignored: inactive days below threshold + active status
            {
                "service": "Linear",
                "monthly_cost": 10,
                "inactive_days": 5,
                "status": "active",
            },
        ]
    )

    assert len(rows) == 3
    assert rows[0]["resource_type"] == "SaaS Subscription"
    assert rows[0]["monthly_waste"] == 25.0  # 5/10 of 50
    assert "unused seats" in rows[0]["explainability_notes"]

    assert rows[1]["resource_name"] == "Datadog"
    assert rows[1]["monthly_waste"] == 30.0
    assert rows[1]["explainability_notes"] == "subscription status is cancelled"

    assert rows[2]["resource_name"] == "Notion"
    assert rows[2]["monthly_waste"] == 12.0
    assert rows[2]["explainability_notes"] == "no activity for 45 days"
