import pytest
from unittest.mock import MagicMock, patch

from app.modules.optimization.domain.azure_provider.plugins.orphaned_images import AzureOrphanedImagesPlugin
from app.modules.optimization.domain.gcp_provider.plugins.unused_ips import GCPUnusedStaticIpsPlugin
from app.modules.optimization.domain.gcp_provider.plugins.machine_images import GCPMachineImagesPlugin
from app.modules.optimization.domain.azure_provider.detector import AzureZombieDetector
from app.modules.optimization.domain.gcp_provider.detector import GCPZombieDetector

@pytest.mark.asyncio
async def test_azure_orphaned_images_plugin_scan():
    client = MagicMock()
    # Mock some images
    img1 = MagicMock()
    img1.id = "img1"
    img1.name = "old-image"
    img1.location = "eastus"
    img1.tags = {}
    
    img2 = MagicMock()
    img2.id = "img2"
    img2.name = "prod-image"
    img2.location = "eastus"
    img2.tags = {"environment": "prod"} # Plugin expects "prod"
    
    # Mock async iterator for client.images.list()
    class AsyncIter:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    client.images.list.return_value = AsyncIter([img1, img2])
    
    plugin = AzureOrphanedImagesPlugin()
    results = await plugin.scan(client)
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "img1"
    assert results[0]["name"] == "old-image"
    assert results[0]["monthly_cost"] == 1.5 # 30 * 0.05

@pytest.mark.asyncio
async def test_gcp_unused_ips_plugin_scan():
    client = MagicMock()
    # Mock GCP address
    addr1 = MagicMock()
    addr1.id = 12345
    addr1.name = "unused-ip"
    addr1.address = "1.2.3.4"
    addr1.status = "RESERVED"
    addr1.labels = {}
    addr1.creation_timestamp = "2023-01-01T00:00:00Z"
    
    addr2 = MagicMock()
    addr2.id = 67890
    addr2.name = "used-ip"
    addr2.address = "5.6.7.8"
    addr2.status = "IN_USE"
    addr2.labels = {}
    
    # GCP SDK usually returns list results
    client.list.return_value = [addr1, addr2]
    
    plugin = GCPUnusedStaticIpsPlugin()
    results = await plugin.scan(client, project_id="test-proj", region="us-central1")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "12345"
    assert results[0]["name"] == "unused-ip"
    assert results[0]["monthly_waste"] == 7.3

@pytest.mark.asyncio
async def test_gcp_machine_images_plugin_scan():
    client = MagicMock()
    # Mock GCP machine image
    img1 = MagicMock()
    img1.id = 11111
    img1.name = "test-machine-image"
    img1.labels = {}
    img1.storage_locations = ["us"]
    img1.creation_timestamp = "2023-01-01T00:00:00Z"
    
    img2 = MagicMock()
    img2.id = 22222
    img2.name = "protected-image"
    img2.labels = {"protected": "true"}
    img2.storage_locations = ["us"]
    
    client.list.return_value = [img1, img2]
    
    plugin = GCPMachineImagesPlugin()
    results = await plugin.scan(client, project_id="test-proj")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "11111"
    assert results[0]["name"] == "test-machine-image"
    assert results[0]["monthly_waste"] == 1.50

@pytest.mark.asyncio
async def test_azure_detector_lifecycle():
    # Use credentials dict as expected by AzureZombieDetector
    creds = {
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "subscription_id": "test-sub"
    }
    
    mock_creds = MagicMock()
    with patch("azure.identity.aio.ClientSecretCredential", return_value=mock_creds), \
         patch("azure.mgmt.compute.aio.ComputeManagementClient"), \
         patch("azure.mgmt.network.aio.NetworkManagementClient"):
        
        async with AzureZombieDetector(region="eastus", credentials=creds) as detector:
            assert detector.subscription_id == "test-sub"
            assert detector._credential is not None
            
        # Verify clients are closed in __aexit__ (implied if no error)

@pytest.mark.asyncio
async def test_gcp_detector_initialization():
    # Pass zone and credentials as expected by GCPZombieDetector
    detector = GCPZombieDetector(region="us-central1-a", credentials={"project_id": "test-proj"})
    
    assert detector.project_id == "test-proj"
    # Clients are lazy-initialized in _execute_plugin_scan
    assert detector._address_client is None
    assert detector._images_client is None
