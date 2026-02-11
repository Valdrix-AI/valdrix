from typing import List, Dict, Any, Optional
import structlog
from azure.identity.aio import ClientSecretCredential
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
    ALLOWED_PLUGIN_CATEGORIES = {
        "idle_azure_vms",
        "idle_azure_gpu_vms",
        "unattached_azure_disks",
        "old_azure_snapshots",
        "orphan_azure_ips",
        "orphan_azure_nics",
        "orphan_azure_nsgs",
        "idle_azure_sql",
        "idle_azure_aks",
        "unused_azure_app_service_plans",
    }

    def __init__(self, region: str = "global", credentials: Optional[Dict[str, Any]] = None, db: Optional[Any] = None, connection: Any = None):
        super().__init__(region, credentials, db, connection)
        # credentials dict expected to have: tenant_id, client_id, client_secret, subscription_id
        self.subscription_id = None
        self._credential = None
        self._credential_error = None

        def _build_credential(tenant_id: Optional[str], client_id: Optional[str], client_secret: Optional[str]):
            if not tenant_id or not client_id or not client_secret:
                self._credential_error = "missing_client_credentials"
                logger.warning(
                    "azure_detector_missing_auth_fields",
                    has_tenant=bool(tenant_id),
                    has_client_id=bool(client_id),
                    has_client_secret=bool(client_secret)
                )
                return None
            try:
                return ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret
                )
            except Exception as exc:
                self._credential_error = str(exc)
                logger.error("azure_detector_credential_init_failed", error=str(exc))
                return None

        if connection:
            # Use logic from connection or adapter to get creds
            self.subscription_id = connection.subscription_id
            self._credential = _build_credential(
                connection.azure_tenant_id,
                connection.client_id,
                connection.client_secret
            )
        elif credentials:
            self.subscription_id = credentials.get("subscription_id")
            self._credential = _build_credential(
                credentials.get("tenant_id"),
                credentials.get("client_id"),
                credentials.get("client_secret")
            )
        
        if not self.subscription_id:
            logger.warning("azure_detector_missing_subscription_id")
        
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
        plugins = registry.get_plugins_for_provider("azure")
        self.plugins = [p for p in plugins if p.category_key in self.ALLOWED_PLUGIN_CATEGORIES]
        skipped = sorted({p.category_key for p in plugins if p.category_key not in self.ALLOWED_PLUGIN_CATEGORIES})
        if skipped:
            logger.warning("azure_detector_skipping_noncanonical_plugins", categories=skipped)

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute Azure plugin scan, passing the appropriate client.
        """
        if not self._credential or not self.subscription_id:
            logger.error(
                "azure_detector_missing_credentials",
                subscription_id=bool(self.subscription_id),
                credential_ready=bool(self._credential),
                error=self._credential_error
            )
            return []
        try:
            results = await plugin.scan(
                subscription_id=self.subscription_id,
                credentials=self._credential,
                region=self.region
            )
        except Exception as exc:
            logger.error("azure_plugin_scan_failed", plugin=plugin.category_key, error=str(exc))
            return []
        if results is None:
            logger.warning("azure_plugin_scan_returned_none", plugin=plugin.category_key)
            return []
        if not isinstance(results, list):
            logger.warning("azure_plugin_scan_invalid_result", plugin=plugin.category_key, result_type=type(results).__name__)
            return []
        return results

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
