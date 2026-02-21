
import pytest
from unittest.mock import MagicMock, patch
import sys

# -----------------------------------------------------------------------------
# Test: IdleVertexEndpointsPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_vertex_endpoints_plugin_scan(mock_gcp_creds):
    """
    TDD: Verify detecting an idle Vertex AI Endpoint (Traffic split exists but 0 predictions).
    """
    # Mock GCP SDKs globally for this test context
    with patch.dict(sys.modules, {
        "google.cloud": MagicMock(),
        "google.cloud.aiplatform": MagicMock(),
        "google.oauth2": MagicMock(),
    }):
        from app.modules.optimization.adapters.gcp.plugins.ai import IdleVertexEndpointsPlugin
        
        plugin = IdleVertexEndpointsPlugin()
        assert plugin.category_key == "idle_vertex_ai_endpoints"

        # Mock AIPlatform Client
        mock_client = MagicMock()
        
        # Mock Endpoint
        mock_endpoint = MagicMock()
        mock_endpoint.name = "projects/123/locations/us-central1/endpoints/456"
        mock_endpoint.display_name = "unused-model-endpoint"
        # Traffic split implies it's "active" / deployed
        mock_endpoint.traffic_split = {"deployed_model_1": 100} 
        
        mock_client.list_endpoints.return_value = [mock_endpoint]

        # Mock Metrics (Monitoring Client) to return 0 prediction count
        # (Simplified mock structure for TDD)
        # We assume the plugin calls some metric service or the endpoint itself has metric accessors
        # For this TDD, let's assume we use the MonitoringClient
        
        mock_monitor = MagicMock()
        # Mocking empty time series for "aiplatform.googleapis.com/endpoint/prediction_count"
        mock_monitor.list_time_series.return_value = [] 

        with patch(
            "app.modules.optimization.adapters.gcp.plugins.ai.aiplatform_v1.EndpointServiceClient",
            return_value=mock_client,
            create=True,
        ), \
             patch("app.modules.optimization.adapters.gcp.plugins.ai.service_account", MagicMock()), \
             patch("app.modules.optimization.adapters.gcp.plugins.ai.monitoring_v3.MetricServiceClient", return_value=mock_monitor):
            
            zombies = await plugin.scan(
                "project-id",
                "us-central1",
                credentials=mock_gcp_creds
            )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_endpoint.name
    assert z["resource_type"] == "Vertex AI Endpoint"
    assert z["action"] == "undeploy_vertex_endpoint"
    assert "monthly_cost" in z

# -----------------------------------------------------------------------------
# Test: IdleVectorSearchPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_vector_search_plugin_scan(mock_gcp_creds):
    """
    TDD: Verify detecting an idle Vertex AI Vector Search Index Endpoint.
    """
    with patch.dict(sys.modules, {
        "google.cloud": MagicMock(),
        "google.cloud.aiplatform": MagicMock(),
        "google.oauth2": MagicMock(),
    }):
        from app.modules.optimization.adapters.gcp.plugins.search import IdleVectorSearchPlugin
        
        plugin = IdleVectorSearchPlugin()
        assert plugin.category_key == "idle_vector_search_indices"

        # Mock Index Endpoint
        mock_idx_endpoint = MagicMock()
        mock_idx_endpoint.name = "projects/123/locations/us-central1/indexEndpoints/789"
        mock_idx_endpoint.display_name = "unused-vector-index"
        # Has deployed index
        mock_deployed_index = MagicMock()
        mock_deployed_index.id = "deployed_index_1"
        mock_idx_endpoint.deployed_indexes = [mock_deployed_index]

        mock_client = MagicMock()
        mock_client.list_index_endpoints.return_value = [mock_idx_endpoint]

        # Mock Metrics (0 queries)
        mock_monitor = MagicMock()
        mock_monitor.list_time_series.return_value = [] 

        with patch(
            "app.modules.optimization.adapters.gcp.plugins.search.aiplatform_v1.IndexEndpointServiceClient",
            return_value=mock_client,
            create=True,
        ), \
             patch("app.modules.optimization.adapters.gcp.plugins.search.service_account", MagicMock()), \
             patch("app.modules.optimization.adapters.gcp.plugins.search.monitoring_v3.MetricServiceClient", return_value=mock_monitor):

            zombies = await plugin.scan(
                "project-id",
                "us-central1",
                credentials=mock_gcp_creds
            )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_idx_endpoint.name
    assert z["resource_type"] == "Vertex AI Vector Index"
    assert z["action"] == "undeploy_vector_index"
    assert "monthly_cost" in z
