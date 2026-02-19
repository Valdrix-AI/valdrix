
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from datetime import datetime

# -----------------------------------------------------------------------------
# Test: OverprovisionedVmPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overprovisioned_vm_plugin_scan(mock_azure_creds):
    """
    TDD: Verify detecting an Active but Overprovisioned Azure VM.
    Scenario: VM is 'running', Max CPU < 10% over 7 days.
    """
    # Mock Azure SDKs globally
    with patch.dict(sys.modules, {
        "azure.mgmt.compute": MagicMock(),
        "azure.mgmt.monitor": MagicMock(),
        "azure.core": MagicMock(),
    }):
        from app.modules.optimization.adapters.azure.plugins.rightsizing import OverprovisionedVmPlugin
        
        plugin = OverprovisionedVmPlugin()
        assert plugin.category_key == "overprovisioned_azure_vms"
        
        # Mock Compute Client
        mock_compute_client = MagicMock()
        
        # Mock VM
        mock_vm = MagicMock()
        mock_vm.id = "/subscriptions/123/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-heavy"
        mock_vm.name = "vm-heavy"
        mock_vm.location = "eastus"
        mock_vm.hardware_profile.vm_size = "Standard_D4s_v3" # Large
        # Tags are usually a dict or object in SDK, let's assume dict for this test adapter
        mock_vm.tags = {"Environment": "Prod"}
        
        # Mock Instance View (State)
        mock_instance_view = MagicMock()
        mock_status = MagicMock()
        mock_status.code = "PowerState/running"
        mock_instance_view.statuses = [mock_status]
        
        # We need to mock instance view retrieval if the plugin checks state
        # Or does the plugin assume list_all returns state? 
        # Usually requires `expand='instanceView'` or separate call.
        # Let's assume plugin calls get_instance_view or list with expand.
        
        mock_compute_client.virtual_machines.list_all.return_value = [mock_vm]
        # Allow checking state via separate call if needed, or if list provides it
        mock_compute_client.virtual_machines.instance_view.return_value = mock_instance_view

        # Mock Monitor Client (Metrics)
        mock_monitor_client = MagicMock()
        
        # Metric Response Structure
        # Timeseries -> Data -> Points
        mock_metric_val = MagicMock()
        mock_metric_val.average = None # We look for Maximum? Or Average?
        mock_metric_val.maximum = 5.0 # Max CPU is 5% (Overprovisioned)
        mock_metric_val.time_stamp = datetime.now()
        
        mock_timeseries = MagicMock()
        mock_timeseries.data = [mock_metric_val]
        
        mock_metric_obj = MagicMock()
        mock_metric_obj.timeseries = [mock_timeseries]
        mock_metric_obj.name.value = "Percentage CPU"
        
        mock_monitor_client.metrics.list.return_value.value = [mock_metric_obj]

        # Patch the Client creation context managers or constructors
        with patch("app.modules.optimization.adapters.azure.plugins.rightsizing.ComputeManagementClient", return_value=mock_compute_client), \
             patch("app.modules.optimization.adapters.azure.plugins.rightsizing.MonitorManagementClient", return_value=mock_monitor_client):
            
            zombies = await plugin.scan(
                session="sub-id",
                credentials=mock_azure_creds
            )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_vm.id
    assert z["resource_type"] == "Azure Virtual Machine"
    assert "Standard_D4s_v3" in z["recommendation"]
    assert "Max CPU" in z["explainability_notes"]
    assert z["confidence_score"] > 0.8
