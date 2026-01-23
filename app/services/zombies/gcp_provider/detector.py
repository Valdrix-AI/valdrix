from typing import List, Dict, Any, Optional
import structlog
from google.cloud import compute_v1
from google.cloud import logging as gcp_logging
# Note: google.oauth2.service_account is needed for custom creds if not using default
from google.oauth2 import service_account
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.zombie_plugin import ZombiePlugin

# Import GCP Plugins
# Import GCP Plugins to trigger registration
import app.services.zombies.gcp_provider.plugins  # noqa

logger = structlog.get_logger()
class GCPZombieDetector(BaseZombieDetector):
    """
    Concrete implementation of ZombieDetector for GCP.
    Manages GCP SDK clients and plugin execution.
    """

    def __init__(self, region: str = "us-central1-a", credentials: Optional[Dict[str, Any]] = None, db: Optional[Any] = None, connection: Any = None):
        # region for GCP is usually a zone like 'us-central1-a'
        super().__init__(region, credentials, db, connection)
        self.project_id = None
        self._credentials_obj = None

        if connection:
            from app.services.adapters.gcp import GCPAdapter
            adapter = GCPAdapter(connection)
            self.project_id = connection.project_id
            # Fetch credentials using logic from connection or adapter
            if connection.service_account_json:
                import json
                info = json.loads(connection.service_account_json)
                self._credentials_obj = service_account.Credentials.from_service_account_info(info)

        elif credentials:
            self.project_id = credentials.get("project_id")
            if credentials.get("service_account_json"):
                import json
                info = json.loads(credentials["service_account_json"])
                self._credentials_obj = service_account.Credentials.from_service_account_info(info)
                if not self.project_id:
                    self.project_id = info.get("project_id")

        self._disks_client = None
        self._address_client = None
        self._images_client = None
        self._logging_client = None

    @property
    def provider_name(self) -> str:
        return "gcp"

    def _initialize_plugins(self):
        """Register the standard suite of GCP detections."""
        self.plugins = registry.get_plugins_for_provider("gcp")

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute GCP plugin scan.
        """
        if not self.project_id:
            logger.error("gcp_detector_missing_project_id")
            return []

        client = None
        kwargs = {"project_id": self.project_id}

        if plugin.category_key == "unattached_disks":
            if not self._disks_client:
                self._disks_client = compute_v1.DisksClient(credentials=self._credentials_obj) if self._credentials_obj else compute_v1.DisksClient()
            client = self._disks_client
            kwargs["zone"] = self.region
            
        elif plugin.category_key == "orphaned_ips":
            if not self._address_client:
                self._address_client = compute_v1.AddressesClient(credentials=self._credentials_obj) if self._credentials_obj else compute_v1.AddressesClient()
            client = self._address_client
            kwargs["region"] = "-".join(self.region.split("-")[:2])
            
        elif plugin.category_key == "orphaned_images":
            if not self._images_client:
                self._images_client = compute_v1.MachineImagesClient(credentials=self._credentials_obj) if self._credentials_obj else compute_v1.MachineImagesClient()
            client = self._images_client

        elif plugin.category_key == "idle_instances":
            if not self._disks_client: # Just a placeholder, we use compute clients
                self._disks_client = compute_v1.InstancesClient(credentials=self._credentials_obj) if self._credentials_obj else compute_v1.InstancesClient()
            if not self._logging_client:
                self._logging_client = gcp_logging.Client(credentials=self._credentials_obj, project=self.project_id) if self._credentials_obj else gcp_logging.Client(project=self.project_id)
            client = self._disks_client
            kwargs["zone"] = self.region
            return await plugin.scan(client, logging_client=self._logging_client, **kwargs)

        if client:
            return await plugin.scan(client, **kwargs)

        return []
