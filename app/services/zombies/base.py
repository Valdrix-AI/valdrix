import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime, timezone
from decimal import Decimal

from app.services.zombies.zombie_plugin import ZombiePlugin

logger = structlog.get_logger()

# Default timeouts
PLUGIN_TIMEOUT_SECONDS = 30
REGION_TIMEOUT_SECONDS = 120

class BaseZombieDetector(ABC):
    """
    Abstract Base Class for multi-cloud zombie resource detection.
    Implements the Strategy Pattern:
    - Base class handles orchestration, aggregation, and error handling.
    - Subclasses (strategies) handle provider-specific API calls.
    """

    def __init__(self, region: str = "global", credentials: Optional[Dict[str, str]] = None):
        self.region = region
        self.credentials = credentials
        self.plugins: List[ZombiePlugin] = [] 

    @abstractmethod
    def _initialize_plugins(self):
        """Register provider-specific plugins."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the cloud provider (e.g., 'aws', 'azure', 'gcp')."""
        pass

    async def scan_all(self, on_category_complete=None) -> Dict[str, Any]:
        """
        Orchestrate the scan across all registered plugins.
        Generic implementation for all providers.
        """
        self._initialize_plugins()
        
        results = {
            "provider": self.provider_name,
            "region": self.region,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "total_monthly_waste": Decimal("0"),
        }

        # Initialize keys
        for plugin in self.plugins:
            results[plugin.category_key] = []

        try:
            # Run plugins in parallel
            tasks = [self._run_plugin_with_timeout(plugin) for plugin in self.plugins]
            
            # Wrap for checkpoints
            async def run_and_checkpoint(task):
                cat_key, items = await task
                if on_category_complete:
                    await on_category_complete(cat_key, items)
                return cat_key, items

            checkpoint_tasks = [run_and_checkpoint(t) for t in tasks]
            plugin_results = await asyncio.gather(*checkpoint_tasks)

            # Aggregate
            for category_key, items in plugin_results:
                results[category_key] = items

            # Calculate total waste
            total = Decimal("0")
            for key, items in results.items():
                if isinstance(items, list):
                    for item in items:
                        total += Decimal(str(item.get("monthly_cost", 0)))
            
            results["total_monthly_waste"] = float(round(total, 2))

            logger.info(
                "zombie_scan_complete",
                provider=self.provider_name,
                waste=results["total_monthly_waste"],
                plugins_run=len(self.plugins)
            )

        except Exception as e:
            logger.error("zombie_scan_failed", provider=self.provider_name, error=str(e))
            results["error"] = str(e)

        return results

    async def _run_plugin_with_timeout(self, plugin: ZombiePlugin) -> tuple[str, List[Dict]]:
        """Run a single plugin with generic timeout protection."""
        try:
            # Subclasses must implement how they pass session/client to plugin
            # We delegate to an abstract method or assume plugin.scan accepts standardized context?
            # Strategy: pass the detector itself or its specialized session property
            
            scan_coro = self._execute_plugin_scan(plugin)
            
            items = await asyncio.wait_for(scan_coro, timeout=PLUGIN_TIMEOUT_SECONDS)
            return plugin.category_key, items
            
        except asyncio.TimeoutError:
            logger.error("plugin_timeout", plugin=plugin.category_key)
            return plugin.category_key, []
        except Exception as e:
            logger.error("plugin_scan_failed", plugin=plugin.category_key, error=str(e))
            return plugin.category_key, []

    @abstractmethod
    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute the plugin scan using provider-specific sessions/clients.
        Must be implemented by subclasses to bridge the generic plugin interface
        with the specific client libraries (boto3, azure-identity, etc).
        """
        pass
