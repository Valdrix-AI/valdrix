
import pytest
from unittest.mock import MagicMock, patch
import sys

# -----------------------------------------------------------------------------
# Test: OverprovisionedComputePlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overprovisioned_compute_plugin_scan(mock_gcp_creds):
    """
    TDD: Verify detecting an Active but Overprovisioned GCP Compute Instance.
    Scenario: Instance is 'RUNNING', 'compute.googleapis.com/instance/cpu/utilization' Max < 0.1 (10%).
    """
    # Mock GCP SDKs globally
    with patch.dict(sys.modules, {
        "google.cloud": MagicMock(),
        "google.cloud.compute_v1": MagicMock(),
        "google.cloud.monitoring_v3": MagicMock(),
        "google.oauth2": MagicMock(),
    }):
        from app.modules.optimization.adapters.gcp.plugins.rightsizing import OverprovisionedComputePlugin
        
        plugin = OverprovisionedComputePlugin()
        assert plugin.category_key == "overprovisioned_gcp_instances"
        
        # Mock Compute Client
        mock_instances_client = MagicMock()
        
        # Mock Instance
        mock_instance = MagicMock()
        mock_instance.name = "gcp-heavy-vm"
        mock_instance.id = 123456789
        mock_instance.zone = "us-central1-a"
        mock_instance.machine_type = "https://www.googleapis.com/compute/v1/projects/my-project/zones/us-central1-a/machineTypes/e2-standard-4"
        mock_instance.status = "RUNNING"
        
        # Aggregated List returns items as dict {zone: list}
        MagicMock()
        # The client returns an iterable where each item has 'instances' attribute
        mock_page = MagicMock()
        mock_page.instances = [mock_instance]
        mock_instances_client.aggregated_list.return_value = [("zones/us-central1-a", mock_page)]

        # Mock Monitor Client
        mock_monitor_client = MagicMock()
        
        # Metric Response
        # TimeSeries -> points -> value -> double_value
        mock_point = MagicMock()
        mock_point.value.double_value = 0.05 # 5% CPU
        
        mock_ts = MagicMock()
        mock_ts.points = [mock_point]
        
        mock_monitor_client.list_time_series.return_value = [mock_ts]
        
        with patch("app.modules.optimization.adapters.gcp.plugins.rightsizing.compute_v1.InstancesClient", return_value=mock_instances_client), \
             patch("app.modules.optimization.adapters.gcp.plugins.rightsizing.monitoring_v3.MetricServiceClient", return_value=mock_monitor_client):
            
            zombies = await plugin.scan(
                session="project-id",
                credentials=mock_gcp_creds
            )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == str(mock_instance.id)
    assert z["resource_type"] == "GCP Compute Instance"
    assert "e2-standard-4" in z["recommendation"]
    assert "Max CPU" in z["explainability_notes"]
    assert z["confidence_score"] > 0.8
