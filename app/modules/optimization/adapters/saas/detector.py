from typing import Any, Dict, List

import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.registry import registry

# Import plugins to trigger registration.
import app.modules.optimization.adapters.saas.plugins  # noqa

logger = structlog.get_logger()


class SaaSZombieDetector(BaseZombieDetector):
    """
    Zombie detector for SaaS cost feeds.

    Uses feed-level usage/seat metadata to detect underutilized subscriptions.
    """

    ALLOWED_PLUGIN_CATEGORIES = {
        "idle_saas_subscriptions",
    }

    @property
    def provider_name(self) -> str:
        return "saas"

    def _initialize_plugins(self) -> None:
        plugins = registry.get_plugins_for_provider("saas")
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
                "saas_detector_skipping_noncanonical_plugins", categories=skipped
            )

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        cost_feed = (
            getattr(self.connection, "spend_feed", None)
            or getattr(self.connection, "cost_feed", None)
            or []
        )
        results = await plugin.scan(
            session=None,
            region="global",
            credentials=self.credentials,
            cost_feed=cost_feed,
            connection=self.connection,
        )
        if not isinstance(results, list):
            logger.warning(
                "saas_plugin_scan_invalid_result",
                plugin=plugin.category_key,
                result_type=type(results).__name__,
            )
            return []
        return results
