from __future__ import annotations

from unittest.mock import patch

import pytest

from app.modules.optimization.adapters.gcp.plugins.containers import (
    EmptyGkeClusterPlugin,
    IdleCloudFunctionsPlugin,
    IdleCloudRunPlugin,
)


def test_gcp_container_plugin_category_keys() -> None:
    assert EmptyGkeClusterPlugin().category_key == "empty_gke_clusters"
    assert IdleCloudRunPlugin().category_key == "idle_cloud_run"
    assert IdleCloudFunctionsPlugin().category_key == "idle_cloud_functions"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin",
    [EmptyGkeClusterPlugin(), IdleCloudRunPlugin(), IdleCloudFunctionsPlugin()],
)
async def test_gcp_container_plugins_require_project_id_and_warn(plugin) -> None:
    with patch(
        "app.modules.optimization.adapters.gcp.plugins.containers.logger"
    ) as logger_mock:
        out = await plugin.scan("", "us-central1")

    assert out == []
    logger_mock.warning.assert_called_once_with(
        "gcp_scan_missing_project_id", plugin=plugin.category_key
    )


@pytest.mark.asyncio
async def test_idle_cloud_run_without_billing_records_returns_empty() -> None:
    out = await IdleCloudRunPlugin().scan("proj-1", "us-central1")
    assert out == []


@pytest.mark.asyncio
async def test_idle_cloud_functions_billing_records_branch() -> None:
    plugin = IdleCloudFunctionsPlugin()
    with patch("app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer") as analyzer_cls:
        analyzer_cls.return_value.find_idle_cloud_functions.return_value = [
            {"resource_id": "func-1"}
        ]
        out = await plugin.scan("proj-1", "us-central1", billing_records=[{"x": 1}])

    assert out == [{"resource_id": "func-1"}]
    analyzer_cls.return_value.find_idle_cloud_functions.assert_called_once_with(days=30)


@pytest.mark.asyncio
async def test_idle_cloud_functions_without_billing_records_returns_empty() -> None:
    out = await IdleCloudFunctionsPlugin().scan("proj-1", "us-central1")
    assert out == []
