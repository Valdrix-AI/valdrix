from typing import Any, Dict, List

import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.registry import registry

# Import plugins to trigger registration.
import app.modules.optimization.adapters.hybrid.plugins  # noqa

logger = structlog.get_logger()


class HybridZombieDetector(BaseZombieDetector):
    """
    Zombie detector for hybrid/private infrastructure spend feeds.
    """

    ALLOWED_PLUGIN_CATEGORIES = {
        "idle_hybrid_resources",
    }

    @property
    def provider_name(self) -> str:
        return "hybrid"

    def _initialize_plugins(self) -> None:
        plugins = registry.get_plugins_for_provider("hybrid")
        self.plugins = [
            p for p in plugins if p.category_key in self.ALLOWED_PLUGIN_CATEGORIES
        ]
        skipped = sorted(
            {
                p.category_key
                for p in plugins
                if p.category_key not in self.ALLOWED_PLUGIN_CATEGORIES
            }
        )
        if skipped:
            logger.warning(
                "hybrid_detector_skipping_noncanonical_plugins", categories=skipped
            )

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        cost_feed = (
            getattr(self.connection, "spend_feed", None)
            or getattr(self.connection, "cost_feed", None)
            or []
        )
        connector_config = getattr(self.connection, "connector_config", None)
        config = connector_config if isinstance(connector_config, dict) else {}
        credentials = self.credentials if isinstance(self.credentials, dict) else {}
        if not credentials:
            credentials = {
                "vendor": str(getattr(self.connection, "vendor", "") or ""),
                "auth_method": str(getattr(self.connection, "auth_method", "") or ""),
                "api_key": str(getattr(self.connection, "api_key", "") or ""),
                "api_secret": str(getattr(self.connection, "api_secret", "") or ""),
                "connector_config": config,
                "spend_feed": cost_feed if isinstance(cost_feed, list) else [],
            }

        results = await plugin.scan(
            session=None,
            region="global",
            credentials=credentials,
            config=config,
            cost_feed=cost_feed,
            connection=self.connection,
        )
        if not isinstance(results, list):
            logger.warning(
                "hybrid_plugin_scan_invalid_result",
                plugin=plugin.category_key,
                result_type=type(results).__name__,
            )
            return []
        return results
