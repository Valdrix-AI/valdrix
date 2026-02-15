from typing import Any, Dict, List

import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.domain.registry import registry

# Import plugins to trigger registration.
import app.modules.optimization.adapters.license.plugins  # noqa

logger = structlog.get_logger()


class LicenseZombieDetector(BaseZombieDetector):
    """
    Zombie detector for license/ITAM feeds.

    Uses seat allocation and contract status metadata for waste detection.
    """

    ALLOWED_PLUGIN_CATEGORIES = {
        "unused_license_seats",
    }

    @property
    def provider_name(self) -> str:
        return "license"

    def _initialize_plugins(self) -> None:
        plugins = registry.get_plugins_for_provider("license")
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
                "license_detector_skipping_noncanonical_plugins", categories=skipped
            )

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        cost_feed = (
            getattr(self.connection, "license_feed", None)
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
                "license_plugin_scan_invalid_result",
                plugin=plugin.category_key,
                result_type=type(results).__name__,
            )
            return []
        return results
