from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import structlog
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor.aio import MonitorManagementClient
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("azure")
class AzureUnattachedDisksPlugin(ZombiePlugin):
    """
    Detects unattached Managed Disks in Azure.
    """

    @property
    def category_key(self) -> str:
        return "unattached_disks"

    async def scan(self, client: ComputeManagementClient, region: str = None, monitor_client: Optional[MonitorManagementClient] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Scans for disks with state 'Unattached' and 0 IOPS.
        """
        zombies = []
        try:
            async for disk in client.disks.list():
                if region and disk.location.lower() != region.lower():
                    continue

                if disk.disk_state.lower() == "unattached":
                    # Deep-Scan Layer: Check for recent IOPS if monitor client is provided
                    has_recent_activity = False
                    if monitor_client:
                        try:
                            # Check disk metrics (e.g., Disk Read/Write Bytes) for the last 7 days
                            timespan = f"{(datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}/{datetime.now(timezone.utc).isoformat()}"
                            metrics = await monitor_client.metrics.list(
                                resource_uri=disk.id,
                                timespan=timespan,
                                interval="P7D",
                                metricnames="Composite Disk Read Bytes,Composite Disk Write Bytes",
                                aggregation="Total"
                            )
                            for metric in metrics.value:
                                for timeseries in metric.timeseries:
                                    if any(v.total > 0 for v in timeseries.data):
                                        has_recent_activity = True
                                        break
                        except Exception as e:
                            logger.warning("azure_disk_metrics_failed", disk=disk.name, error=str(e))
                    
                    if has_recent_activity:
                        continue

                    size_gb = disk.disk_size_gb or 0
                    sku_name = disk.sku.name if disk.sku else "Standard_LRS"
                    monthly_cost = self._estimate_disk_cost(size_gb, sku_name)
                    
                    zombies.append({
                        "resource_id": disk.id,
                        "name": disk.name,
                        "region": disk.location,
                        "size_gb": size_gb,
                        "sku": sku_name,
                        "monthly_cost": float(monthly_cost),
                        "monthly_waste": float(monthly_cost),
                        "tags": disk.tags or {},
                        "created_at": disk.time_created.isoformat() if disk.time_created else None,
                        "explainability_notes": "Disk is 'Unattached' and has shown 0 IOPS in the last 7 days."
                    })
                    
            return zombies
        except Exception as e:
            logger.error("azure_unattached_disks_scan_failed", error=str(e))
            return []

    def _estimate_disk_cost(self, size_gb: int, sku: str) -> Decimal:
        """
        Rough estimation of monthly disk cost in USD.
        Rates are approximate for us-east (Standard: ~$0.05/GB, Premium: ~$0.15/GB).
        """
        if "Premium" in sku:
            rate = Decimal("0.15")
        elif "Ultra" in sku:
            rate = Decimal("0.20")
        else:
            rate = Decimal("0.05") # Standard
            
        return Decimal(size_gb) * rate
