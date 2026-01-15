from typing import List, Dict, Any
import structlog
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.zombie_plugin import ZombiePlugin

# Import Azure Plugins
from app.services.zombies.az_provider.plugins.unattached_disks import AzureUnattachedDisksPlugin
from app.services.zombies.az_provider.plugins.orphaned_ips import AzureOrphanedIpsPlugin

logger = structlog.get_logger()

class AzureZombieDetector(BaseZombieDetector):
    """
    Concrete implementation of ZombieDetector for Azure.
    Manages Azure SDK clients and plugin execution.
    """

    def __init__(self, region: str = "global", credentials: Dict[str, str] = None):
        super().__init__(region, credentials)
        # credentials dict expected to have: tenant_id, client_id, client_secret, subscription_id
        self.subscription_id = credentials.get("subscription_id") if credentials else None
        self._credential = None
        if credentials:
            self._credential = ClientSecretCredential(
                tenant_id=credentials.get("tenant_id"),
                client_id=credentials.get("client_id"),
                client_secret=credentials.get("client_secret")
            )
        
        # Clients are lazily initialized in scan method if needed, 
        # or we can init them here if we have sub ID.
        self._compute_client = None
        self._network_client = None

    @property
    def provider_name(self) -> str:
        return "azure"

    def _initialize_plugins(self):
        """Register the standard suite of Azure detections."""
        self.plugins = [
            AzureUnattachedDisksPlugin(),
            AzureOrphanedIpsPlugin(),
        ]

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute Azure plugin scan, passing the appropriate client.
        """
        if not self._credential or not self.subscription_id:
            logger.error("azure_detector_missing_credentials")
            return []

        # Route to appropriate client based on plugin type or key
        if plugin.category_key == "unattached_disks":
            if not self._compute_client:
                self._compute_client = ComputeManagementClient(self._credential, self.subscription_id)
            return await plugin.scan(self._compute_client, region=self.region)
            
        elif plugin.category_key == "orphaned_ips":
            if not self._network_client:
                self._network_client = NetworkManagementClient(self._credential, self.subscription_id)
            return await plugin.scan(self._network_client, region=self.region)
            
        return []
