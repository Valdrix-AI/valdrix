from typing import List, Dict, Any, Optional
import structlog
from azure.identity.aio import ClientSecretCredential
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.mgmt.network.aio import NetworkManagementClient
from azure.mgmt.monitor.aio import MonitorManagementClient
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

# Import Azure Plugins to trigger registration
import app.modules.optimization.adapters.azure.plugins  # noqa

logger = structlog.get_logger()

class AzureZombieDetector(BaseZombieDetector):
    """
    Concrete implementation of ZombieDetector for Azure.
    Manages Azure SDK clients and plugin execution.
    """

    def __init__(self, region: str = "global", credentials: Optional[Dict[str, Any]] = None, db: Optional[Any] = None, connection: Any = None):
        super().__init__(region, credentials, db, connection)
        # credentials dict expected to have: tenant_id, client_id, client_secret, subscription_id
        self.subscription_id = None
        self._credential = None

        if connection:
            # Use logic from connection or adapter to get creds
            self.subscription_id = connection.subscription_id
            self._credential = ClientSecretCredential(
                tenant_id=connection.azure_tenant_id,
                client_id=connection.client_id,
                client_secret=connection.client_secret
            )
        elif credentials:
            self.subscription_id = credentials.get("subscription_id")
            self._credential = ClientSecretCredential(
                tenant_id=credentials.get("tenant_id"),
                client_id=credentials.get("client_id"),
                client_secret=credentials.get("client_secret")
            )
        
        # Clients are lazily initialized in scan method if needed, 
        # or we can init them here if we have sub ID.
        self._compute_client = None
        self._network_client = None
        self._monitor_client = None

    @property
    def provider_name(self) -> str:
        return "azure"

    def _initialize_plugins(self):
        """Register the standard suite of Azure detections."""
        self.plugins = registry.get_plugins_for_provider("azure")

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute Azure plugin scan, passing the appropriate client.
        """
        if not self._credential or not self.subscription_id:
            logger.error("azure_detector_missing_credentials")
            return []

        # Route to appropriate client based on plugin type or key
        client = None
        if plugin.category_key in ["unattached_disks", "orphaned_images"]:
            if not self._compute_client:
                self._compute_client = ComputeManagementClient(self._credential, self.subscription_id)
            client = self._compute_client
            
        elif plugin.category_key == "orphaned_ips":
            if not self._network_client:
                self._network_client = NetworkManagementClient(self._credential, self.subscription_id)
            client = self._network_client
            
        elif plugin.category_key == "idle_vms":
            if not self._compute_client:
                self._compute_client = ComputeManagementClient(self._credential, self.subscription_id)
            if not self._monitor_client:
                self._monitor_client = MonitorManagementClient(self._credential, self.subscription_id)
            client = self._compute_client
            # Pass monitor client in registry or as extra kwarg
            return await plugin.scan(client, region=self.region, monitor_client=self._monitor_client)
            
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._compute_client:
            await self._compute_client.close()
        if self._network_client:
            await self._network_client.close()
        if self._monitor_client:
            await self._monitor_client.close()
        if self._credential:
            await self._credential.close()
