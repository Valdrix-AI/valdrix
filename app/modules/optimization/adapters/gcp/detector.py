from typing import List, Dict, Any, Optional
import structlog
from google.oauth2 import service_account
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

# Import GCP Plugins
# Import GCP Plugins to trigger registration
import app.modules.optimization.adapters.gcp.plugins  # noqa

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
        self._credentials_error = None

        if connection:
            self.project_id = connection.project_id
            # Fetch credentials using logic from connection or adapter
            if connection.service_account_json:
                import json
                try:
                    info = json.loads(connection.service_account_json)
                    self._credentials_obj = service_account.Credentials.from_service_account_info(info)
                except Exception as exc:
                    self._credentials_error = str(exc)
                    logger.error("gcp_detector_invalid_service_account_json", error=str(exc))

        elif credentials:
            self.project_id = credentials.get("project_id")
            if credentials.get("service_account_json"):
                import json
                try:
                    info = json.loads(credentials["service_account_json"])
                    self._credentials_obj = service_account.Credentials.from_service_account_info(info)
                    if not self.project_id:
                        self.project_id = info.get("project_id")
                except Exception as exc:
                    self._credentials_error = str(exc)
                    logger.error("gcp_detector_invalid_service_account_json", error=str(exc))

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
        if self._credentials_error:
            logger.error("gcp_detector_credentials_unavailable", error=self._credentials_error)
            return []

        try:
            results = await plugin.scan(
                project_id=self.project_id,
                credentials=self._credentials_obj,
                region=self.region
            )
        except Exception as exc:
            logger.error("gcp_plugin_scan_failed", plugin=plugin.category_key, error=str(exc))
            return []
        if results is None:
            logger.warning("gcp_plugin_scan_returned_none", plugin=plugin.category_key)
            return []
        if not isinstance(results, list):
            logger.warning("gcp_plugin_scan_invalid_result", plugin=plugin.category_key, result_type=type(results).__name__)
            return []
        return results
