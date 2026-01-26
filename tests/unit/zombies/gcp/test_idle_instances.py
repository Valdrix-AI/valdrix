import pytest
from unittest.mock import MagicMock, patch
import sys

# Move import inside tests to avoid top-level side effects
# form app.modules... import ... is removed from here

@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_gpu_detection():
    with patch.dict(sys.modules, {"app.shared.db.session": MagicMock()}):
        from app.modules.optimization.domain.gcp_provider.plugins.idle_instances import GCPIdleInstancePlugin
        plugin = GCPIdleInstancePlugin()
    client = MagicMock()
    
    # Mock Aggregated List result
    mock_inst = MagicMock()
    mock_inst.id = 12345
    mock_inst.name = "gpu-instance"
    mock_inst.status = "RUNNING"
    mock_inst.machine_type = "zones/us-central1-a/machineTypes/a2-highgpu-1g"
    mock_inst.guest_accelerators = []
    mock_inst.labels = {"team": "ml"}
    mock_inst.cpu_platform = "Intel Ice Lake"
    mock_inst.creation_timestamp = "2023-01-01T00:00:00Z"
    
    mock_response = MagicMock()
    mock_response.instances = [mock_inst]
    
    def mock_aggregated_list(**kwargs):
        yield ("zones/us-central1-a", mock_response)
    
    client.aggregated_list = mock_aggregated_list
    
    zombies = await plugin.scan(client, project_id="test-project")
    
    assert len(zombies) == 1
    assert zombies[0]["name"] == "gpu-instance"
    assert zombies[0]["is_gpu"] is True
    assert zombies[0]["confidence_score"] == 0.95
    assert zombies[0]["monthly_waste"] == pytest.approx(1500.0)

@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_attribution():
    with patch.dict(sys.modules, {"app.shared.db.session": MagicMock()}):
        from app.modules.optimization.domain.gcp_provider.plugins.idle_instances import GCPIdleInstancePlugin
        plugin = GCPIdleInstancePlugin()
    client = MagicMock()
    logging_client = MagicMock()
    
    mock_inst = MagicMock()
    mock_inst.id = 123
    mock_inst.name = "test-inst"
    mock_inst.status = "RUNNING"
    mock_inst.machine_type = "zones/us-central1-a/machineTypes/n1-standard-1"
    mock_inst.guest_accelerators = []
    
    mock_response = MagicMock()
    mock_response.instances = [mock_inst]
    
    def mock_aggregated_list(**kwargs):
        yield ("zones/us-central1-a", mock_response)
    client.aggregated_list = mock_aggregated_list
    
    # Mock Logging Entries
    mock_entry = MagicMock()
    mock_entry.payload = {
        "authenticationInfo": {"principalEmail": "user@example.com"}
    }
    
    logging_client.list_entries.return_value = [mock_entry]
    
    zombies = await plugin.scan(client, project_id="test-project", logging_client=logging_client)
    
    assert len(zombies) == 1
    assert zombies[0]["owner"] == "user@example.com"
