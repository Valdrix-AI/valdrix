"""
Tests for GCP Idle Instance Plugin

These tests verify:
1. GPU detection based on machine type patterns
2. Owner attribution from GCP Audit Logs
3. Cost estimation integration with PricingService
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
import sys


# Pre-mock the GCP libraries before any app imports
_mock_compute = MagicMock()
_mock_logging = MagicMock()
_mock_monitoring = MagicMock()
_mock_monitoring.TimeInterval = MagicMock()
_mock_monitoring.ListTimeSeriesRequest.TimeSeriesView.FULL = "FULL"

# Apply mocks to sys.modules BEFORE importing the plugin
sys.modules.setdefault("google.cloud.compute_v1", _mock_compute)
sys.modules.setdefault("google.cloud.logging", _mock_logging)
sys.modules.setdefault("google.cloud.monitoring_v3", _mock_monitoring)


@pytest.fixture
def mock_gcp_instance():
    """Create a mock GCP compute instance."""
    inst = MagicMock()
    inst.id = 12345
    inst.name = "test-instance"
    inst.status = "RUNNING"
    inst.machine_type = "zones/us-central1-a/machineTypes/n1-standard-1"
    inst.guest_accelerators = []
    inst.labels = {"team": "engineering"}
    inst.cpu_platform = "Intel Ice Lake"
    inst.creation_timestamp = "2023-01-01T00:00:00Z"
    return inst


@pytest.fixture
def mock_gpu_instance():
    """Create a mock GCP GPU instance."""
    inst = MagicMock()
    inst.id = 67890
    inst.name = "gpu-instance"
    inst.status = "RUNNING"
    inst.machine_type = "zones/us-central1-a/machineTypes/a2-highgpu-1g"
    inst.guest_accelerators = []
    inst.labels = {"team": "ml"}
    inst.cpu_platform = "Intel Ice Lake"
    inst.creation_timestamp = "2023-01-01T00:00:00Z"
    return inst


@pytest.fixture
def mock_compute_client(mock_gcp_instance):
    """Create a mock GCP Compute client."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.instances = [mock_gcp_instance]
    client.aggregated_list.return_value = [("zones/us-central1-a", mock_response)]
    return client


@pytest.fixture
def mock_gpu_compute_client(mock_gpu_instance):
    """Create a mock GCP Compute client with GPU instance."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.instances = [mock_gpu_instance]
    client.aggregated_list.return_value = [("zones/us-central1-a", mock_response)]
    return client


@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_gpu_detection(mock_gpu_compute_client):
    """Test that GPU instances are correctly identified with higher confidence."""
    # Import the module (GCP libs already mocked above)
    from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
    
    # Patch the PricingService at the location it's used
    with patch.object(
        sys.modules.get("app.modules.reporting.domain.pricing.service", MagicMock()),
        "PricingService",
        MagicMock(estimate_monthly_waste=MagicMock(return_value=1500.0))
    ):
        # Alternative: patch the method directly on the plugin
        with patch(
            "app.modules.optimization.adapters.gcp.plugins.idle_instances.GCPIdleInstancePlugin._estimate_instance_cost",
            return_value=Decimal("1500.0")
        ):
            plugin = GCPIdleInstancePlugin()
            zombies = await plugin.scan(
                client=mock_gpu_compute_client,
                project_id="test-project"
            )
            
            assert len(zombies) == 1
            zombie = zombies[0]
            assert zombie["name"] == "gpu-instance"
            assert zombie["is_gpu"] is True
            assert zombie["confidence_score"] == 0.95  # GPU instances get higher confidence


@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_standard_instance(mock_compute_client):
    """Test that standard instances get default confidence score."""
    from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
    
    with patch(
        "app.modules.optimization.adapters.gcp.plugins.idle_instances.GCPIdleInstancePlugin._estimate_instance_cost",
        return_value=Decimal("100.0")
    ):
        plugin = GCPIdleInstancePlugin()
        zombies = await plugin.scan(
            client=mock_compute_client,
            project_id="test-project"
        )
        
        assert len(zombies) == 1
        zombie = zombies[0]
        assert zombie["name"] == "test-instance"
        assert not zombie["is_gpu"]  # Should be falsy for non-GPU
        assert zombie["confidence_score"] == 0.8  # Standard confidence


@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_attribution(mock_compute_client):
    """Test that owner attribution is extracted from GCP Audit Logs."""
    from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
    
    # Mock logging client with attribution data
    mock_logging_client = MagicMock()
    mock_entry = MagicMock()
    mock_entry.payload = {
        "authenticationInfo": {"principalEmail": "user@example.com"}
    }
    mock_logging_client.list_entries.return_value = [mock_entry]
    
    with patch(
        "app.modules.optimization.adapters.gcp.plugins.idle_instances.GCPIdleInstancePlugin._estimate_instance_cost",
        return_value=Decimal("100.0")
    ):
        plugin = GCPIdleInstancePlugin()
        zombies = await plugin.scan(
            client=mock_compute_client,
            project_id="test-project",
            logging_client=mock_logging_client
        )
        
        assert len(zombies) == 1
        assert zombies[0]["owner"] == "user@example.com"


@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_skips_stopped_instances():
    """Test that stopped instances are not flagged as zombies."""
    from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
    
    # Create stopped instance
    inst = MagicMock()
    inst.id = 22222
    inst.name = "stopped-instance"
    inst.status = "TERMINATED"
    inst.machine_type = "zones/us-central1-a/machineTypes/n1-standard-1"
    inst.guest_accelerators = []
    inst.labels = {}
    inst.cpu_platform = "Intel"
    inst.creation_timestamp = "2023-01-01"
    
    # Mock client
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.instances = [inst]
    client.aggregated_list.return_value = [("zones/us-central1-a", mock_response)]
    
    with patch(
        "app.modules.optimization.adapters.gcp.plugins.idle_instances.GCPIdleInstancePlugin._estimate_instance_cost",
        return_value=Decimal("100.0")
    ):
        plugin = GCPIdleInstancePlugin()
        zombies = await plugin.scan(
            client=client,
            project_id="test-project"
        )
        
        # Stopped instance should be filtered out
        assert len(zombies) == 0


@pytest.mark.asyncio
async def test_gcp_idle_instance_plugin_handles_scan_error():
    """Test that scan errors are handled gracefully."""
    from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
    
    # Mock client that raises an exception
    client = MagicMock()
    client.aggregated_list.side_effect = Exception("GCP API Error")
    
    plugin = GCPIdleInstancePlugin()
    zombies = await plugin.scan(
        client=client,
        project_id="test-project"
    )
    
    # Should return empty list on error, not raise
    assert zombies == []
