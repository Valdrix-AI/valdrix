from typing import List, Dict, Any
import structlog
from google.cloud import compute_v1
# Note: google.oauth2.service_account is needed for custom creds if not using default
from google.oauth2 import service_account
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.zombie_plugin import ZombiePlugin

# Import GCP Plugins
from app.services.zombies.gcp_provider.plugins.unattached_disks import GCPUnattachedDisksPlugin

logger = structlog.get_logger()

class GCPZombieDetector(BaseZombieDetector):
    """
    Concrete implementation of ZombieDetector for GCP.
    Manages GCP SDK clients and plugin execution.
    """

    def __init__(self, region: str = "us-central1-a", credentials: Dict[str, Any] = None):
        # region for GCP is usually a zone like 'us-central1-a'
        super().__init__(region, credentials)
        self.project_id = credentials.get("project_id") if credentials else None
        
        self._credentials_obj = None
        if credentials and "service_account_json" in credentials:
            import json
            info = json.loads(credentials["service_account_json"])
            self._credentials_obj = service_account.Credentials.from_service_account_info(info)
            if not self.project_id:
                self.project_id = info.get("project_id")

        self._disks_client = None

    @property
    def provider_name(self) -> str:
        return "gcp"

    def _initialize_plugins(self):
        """Register the standard suite of GCP detections."""
        self.plugins = [
            GCPUnattachedDisksPlugin(),
        ]

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute GCP plugin scan.
        """
        if not self.project_id:
            logger.error("gcp_detector_missing_project_id")
            return []

        if plugin.category_key == "unattached_disks":
            if not self._disks_client:
                # GCP SDK clients are usually initialized with credentials
                if self._credentials_obj:
                    self._disks_client = compute_v1.DisksClient(credentials=self._credentials_obj)
                else:
                    self._disks_client = compute_v1.DisksClient()
                    
            return await plugin.scan(self._disks_client, project_id=self.project_id, zone=self.region)
            
        return []
