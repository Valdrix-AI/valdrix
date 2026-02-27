from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.optimization.adapters.gcp.plugins import network as network_module
from app.modules.optimization.adapters.gcp.plugins.network import OrphanExternalIpsPlugin
from app.modules.optimization.adapters.gcp.plugins.search import IdleVectorSearchPlugin


def test_resolve_gcp_credentials_helper_branches() -> None:
    class _FakeGoogleCreds:
        pass

    fake_google_cred = _FakeGoogleCreds()
    fake_other = object()

    with (
        patch.object(network_module, "GoogleCredentials", _FakeGoogleCreds),
        patch.object(
            network_module.service_account.Credentials,
            "from_service_account_info",
            return_value="creds-from-dict",
        ) as from_info,
    ):
        assert network_module._resolve_gcp_credentials(None) is None
        assert network_module._resolve_gcp_credentials({"client_email": "x"}) == "creds-from-dict"
        assert network_module._resolve_gcp_credentials(fake_google_cred) is fake_google_cred
        assert network_module._resolve_gcp_credentials(fake_other) is fake_other

    from_info.assert_called_once()


@pytest.mark.asyncio
async def test_gcp_network_plugin_missing_project_and_billing_records_paths() -> None:
    plugin = OrphanExternalIpsPlugin()
    assert plugin.category_key == "orphan_gcp_ips"

    with patch("app.modules.optimization.adapters.gcp.plugins.network.logger.warning") as warning:
        assert await plugin.scan(session="", region="us-central1") == []
        warning.assert_called_once()

    with patch("app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer") as analyzer_cls:
        analyzer_cls.return_value.find_orphan_ips.return_value = [{"resource_id": "ip-1"}]
        rows = await plugin.scan(
            session="proj-1",
            region="us-central1",
            billing_records=[{"x": 1}],
        )
    assert rows == [{"resource_id": "ip-1"}]


@pytest.mark.asyncio
async def test_gcp_network_plugin_skips_empty_and_non_reserved_addresses() -> None:
    plugin = OrphanExternalIpsPlugin()
    client = MagicMock()
    client.aggregated_list.return_value = [
        ("regions/us-central1", SimpleNamespace(addresses=None)),
        (
            "regions/us-central1",
            SimpleNamespace(
                addresses=[SimpleNamespace(name="ip-2", status="IN_USE", address="35.1.2.4")]
            ),
        ),
    ]

    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AddressesClient",
            return_value=client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AggregatedListAddressesRequest",
            return_value=MagicMock(),
        ),
    ):
        rows = await plugin.scan(
            session="proj-1",
            region="us-central1",
            credentials=MagicMock(),
        )

    assert rows == []


@pytest.mark.asyncio
async def test_gcp_vector_search_plugin_branches_no_creds_and_budget_exhaustion_and_errors() -> None:
    plugin = IdleVectorSearchPlugin()
    assert plugin.category_key == "idle_vector_search_indices"

    endpoint_with_deployed = SimpleNamespace(
        name="projects/p1/locations/us-central1/indexEndpoints/ie-1",
        display_name="ie-1",
        deployed_indexes=[SimpleNamespace(id="d1")],
    )
    endpoint_without_deployed = SimpleNamespace(
        name="projects/p1/locations/us-central1/indexEndpoints/ie-2",
        display_name="ie-2",
        deployed_indexes=[],
    )

    aiplatform_client = MagicMock()
    monitor_client = MagicMock()

    aiplatform_client.list_index_endpoints.return_value = [endpoint_without_deployed]
    monitor_client.list_time_series.return_value = []

    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            return_value=aiplatform_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.MetricServiceClient",
            return_value=monitor_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.TimeInterval",
            side_effect=lambda payload: payload,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.allow_expensive_cloud_api_call",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            network_module.service_account.Credentials,
            "from_service_account_info",
            side_effect=AssertionError("should not be called"),
        ),
    ):
        rows = await plugin.scan("proj-1", "global", credentials=None)
    assert rows == []
    monitor_client.list_time_series.assert_not_called()

    aiplatform_client.list_index_endpoints.return_value = [endpoint_with_deployed]
    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            return_value=aiplatform_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.MetricServiceClient",
            return_value=monitor_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.TimeInterval",
            side_effect=lambda payload: payload,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.allow_expensive_cloud_api_call",
            new=AsyncMock(return_value=False),
        ),
        patch("app.modules.optimization.adapters.gcp.plugins.search.logger.warning") as warning,
    ):
        rows = await plugin.scan("proj-1", "us-central1", credentials={})
    assert rows == []
    warning.assert_called_once()

    monitor_client.list_time_series.return_value = [SimpleNamespace(points=[SimpleNamespace()])]
    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            return_value=aiplatform_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.MetricServiceClient",
            return_value=monitor_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.TimeInterval",
            side_effect=lambda payload: payload,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.allow_expensive_cloud_api_call",
            new=AsyncMock(return_value=True),
        ),
    ):
        rows = await plugin.scan("proj-1", "us-central1", credentials={})
    assert rows == []

    monitor_client.list_time_series.return_value = [SimpleNamespace(points=[])]
    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            return_value=aiplatform_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.MetricServiceClient",
            return_value=monitor_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.TimeInterval",
            side_effect=lambda payload: payload,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.allow_expensive_cloud_api_call",
            new=AsyncMock(return_value=True),
        ),
    ):
        rows = await plugin.scan("proj-1", "us-central1", credentials={})
    assert len(rows) == 1

    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.modules.optimization.adapters.gcp.plugins.search.logger.error") as error,
    ):
        rows = await plugin.scan("proj-1", "us-central1", credentials={})
    assert rows == []
    error.assert_called_once()
