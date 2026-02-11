import pytest
from unittest.mock import MagicMock, patch
from app.modules.optimization.adapters.gcp.plugins.compute import IdleVmsPlugin, IdleGpuInstancesPlugin

@pytest.mark.asyncio
async def test_gcp_idle_vms_scan_fallback():
    """Test GCP idle VMs via Cloud Asset Inventory fallback."""
    plugin = IdleVmsPlugin()
    
    mock_instance = MagicMock()
    mock_instance.name = "vm-1"
    mock_instance.status = "RUNNING"
    mock_instance.guest_accelerators = []
    mock_instance.machine_type = "e2-medium"
    
    mock_client = MagicMock()
    mock_client.aggregated_list.return_value = [
        ("zones/us-central1-a", MagicMock(instances=[mock_instance]))
    ]
    
    with patch("app.modules.optimization.adapters.gcp.plugins.compute.compute_v1.InstancesClient") as mock_client_class:
        mock_client_class.return_value = mock_client
        
        # 1. Standard VM (not flagged without billing data)
        zombies = await plugin.scan(project_id="project-1")
        assert len(zombies) == 0
        
        # 2. GPU VM (flagged as high value)
        mock_instance.guest_accelerators = ["nvidia-tesla-t4"]
        zombies = await plugin.scan(project_id="project-1")
        assert len(zombies) == 1
        assert "GPU" in zombies[0]["resource_type"]
        assert zombies[0]["resource_name"] == "vm-1"

@pytest.mark.asyncio
async def test_gcp_idle_vms_scan_billing():
    """Test GCP idle VMs via billing records."""
    plugin = IdleVmsPlugin()
    
    billing_records = [{"resource_id": "r1", "cost": 10.0}]
    
    with patch("app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer") as mock_analyzer_class:
        mock_analyzer = mock_analyzer_class.return_value
        mock_analyzer.find_idle_vms.return_value = [{"resource_id": "vm-1", "monthly_waste": 100.0}]
        
        zombies = await plugin.scan(project_id="project-1", billing_records=billing_records)
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "vm-1"

@pytest.mark.asyncio
async def test_gcp_gpu_instances_plugin():
    """Test GCP GPU specific plugin."""
    plugin = IdleGpuInstancesPlugin()
    
    billing_records = [{"resource_id": "r1", "cost": 10.0}]
    
    with patch("app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer") as mock_analyzer_class:
        mock_analyzer = mock_analyzer_class.return_value
        mock_analyzer.find_idle_vms.return_value = [
            {"resource_id": "vm-1", "resource_type": "Compute Engine VM (GPU)"},
            {"resource_id": "vm-2", "resource_type": "Compute Engine VM"}
        ]
        
        zombies = await plugin.scan(project_id="project-1", billing_records=billing_records)
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "vm-1"
        
        # Test no billing records
        zombies = await plugin.scan(project_id="project-1")
        assert len(zombies) == 0
