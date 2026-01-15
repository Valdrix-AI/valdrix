"""
Zombie Resource Detector

Detects zombie (unused/underutilized) AWS resources using a plugin architecture.
Scans multiple resource types in parallel for improved performance.

Usage:
    detector = ZombieDetector()
    zombies = await detector.scan_all()

For multi-tenant (uses STS credentials):
    detector = ZombieDetector(region=region, credentials=creds)
"""

import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
import aioboto3
import structlog

from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.zombies.aws.plugins import (
    UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin,
    UnusedElasticIpsPlugin, IdleInstancesPlugin,
    OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin,
    IdleRdsPlugin, ColdRedshiftPlugin,
    IdleSageMakerPlugin,
    LegacyEcrImagesPlugin
)

logger = structlog.get_logger()

# Plugin timeout - prevents any single plugin from blocking the entire scan
PLUGIN_TIMEOUT_SECONDS = 30


class ZombieDetector:
    """
    Detects zombie (unused/underutilized) AWS resources using a plugin system.

    Usage:
        detector = ZombieDetector()
        zombies = await detector.scan_all()

    For multi-tenant (uses STS credentials):
        detector = ZombieDetector(region=region, credentials=creds)
    """

    def __init__(self, region: str = None, credentials: Dict[str, str] = None):
        # Default region removed - should be explicitly provided for clarity
        self.region = region or "us-east-1"  # Legacy fallback, prefer explicit
        self.credentials = credentials
        self.session = aioboto3.Session()
        self.plugins: List[ZombiePlugin] = [
            UnattachedVolumesPlugin(),
            OldSnapshotsPlugin(),
            UnusedElasticIpsPlugin(),
            IdleInstancesPlugin(),
            OrphanLoadBalancersPlugin(),
            IdleRdsPlugin(),
            UnderusedNatGatewaysPlugin(),
            IdleS3BucketsPlugin(),
            LegacyEcrImagesPlugin(),
            IdleSageMakerPlugin(),
            ColdRedshiftPlugin(),
        ]

    async def _run_plugin_with_timeout(self, plugin: ZombiePlugin) -> tuple[str, List[Dict]]:
        """Run a single plugin with timeout protection."""
        try:
            results = await asyncio.wait_for(
                plugin.scan(self.session, self.region, self.credentials),
                timeout=PLUGIN_TIMEOUT_SECONDS
            )
            return plugin.category_key, results
        except asyncio.TimeoutError:
            logger.error("plugin_timeout", plugin=plugin.category_key, timeout=PLUGIN_TIMEOUT_SECONDS)
            return plugin.category_key, []
        except Exception as e:
            logger.error("plugin_scan_failed", plugin=plugin.category_key, error=str(e))
            return plugin.category_key, []

    async def scan_all(self, on_category_complete=None) -> Dict[str, Any]:
        """
        Scan for all types of zombie resources using registered plugins.

        Runs plugins in PARALLEL for improved performance at scale.
        Returns dict with zombies by category and total waste estimate.
        
        Args:
            on_category_complete: Async callback called after each plugin completes.
                                  Used for durable checkpoints.
        """
        zombies = {
            "region": self.region,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "total_monthly_waste": Decimal("0"),
        }

        # Initialize default empty lists
        for plugin in self.plugins:
            zombies[plugin.category_key] = []

        try:
            # Run all plugins in PARALLEL with timeout per plugin
            tasks = [self._run_plugin_with_timeout(plugin) for plugin in self.plugins]
            
            # Wrap tasks to call checkpoint callback
            async def run_and_checkpoint(task):
                category_key, items = await task
                if on_category_complete:
                    await on_category_complete(category_key, items)
                return category_key, items

            checkpoint_tasks = [run_and_checkpoint(t) for t in tasks]
            results = await asyncio.gather(*checkpoint_tasks)

            # Collect results from parallel execution
            for category_key, items in results:
                zombies[category_key] = items

            # Calculate total waste
            total = Decimal("0")
            for key, items in zombies.items():
                if isinstance(items, list):
                    for item in items:
                        total += Decimal(str(item.get("monthly_cost", 0)))

            zombies["total_monthly_waste"] = float(round(total, 2))

            logger.info(
                "zombie_scan_complete",
                waste=zombies["total_monthly_waste"],
                plugins_run=len(self.plugins),
            )

        except Exception as e:
            logger.error("zombie_scan_failed", error=str(e))
            zombies["error"] = str(e)

        return zombies

    async def scan_all_regions(self, regions: List[str]) -> Dict[str, Any]:
        """
        Scan multiple regions in PARALLEL.

        Uses the same parallel plugin execution within each region,
        and runs all regions concurrently with a per-region timeout.

        Args:
            regions: List of AWS region codes to scan

        Returns:
            Aggregated results with per-region breakdown and totals
        """
        REGION_TIMEOUT_SECONDS = 120  # 2 minutes per region

        async def scan_region(region: str) -> Dict[str, Any]:
            """Scan a single region with timeout protection."""
            try:
                detector = ZombieDetector(region=region, credentials=self.credentials)
                return await asyncio.wait_for(
                    detector.scan_all(),
                    timeout=REGION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error("region_scan_timeout", region=region, timeout=REGION_TIMEOUT_SECONDS)
                return {"region": region, "error": "timeout", "total_monthly_waste": 0}
            except Exception as e:
                logger.error("region_scan_failed", region=region, error=str(e))
                return {"region": region, "error": str(e), "total_monthly_waste": 0}

        # Run all regions in parallel
        tasks = [scan_region(region) for region in regions]
        region_results = await asyncio.gather(*tasks)

        # Aggregate results
        aggregated = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "regions_scanned": len(regions),
            "regions": region_results,
            "total_monthly_waste": sum(
                float(r.get("total_monthly_waste", 0)) for r in region_results
            ),
            "errors": [r.get("error") for r in region_results if r.get("error")]
        }

        logger.info(
            "multi_region_scan_complete",
            regions_scanned=len(regions),
            total_waste=aggregated["total_monthly_waste"],
            errors=len(aggregated["errors"])
        )

        return aggregated
