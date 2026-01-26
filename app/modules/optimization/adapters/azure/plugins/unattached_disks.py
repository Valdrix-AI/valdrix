from typing import List, Dict, Any
import structlog
from azure.mgmt.compute import ComputeManagementClient
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

    async def scan(self, client: ComputeManagementClient, region: str = None, credentials: Any = None) -> List[Dict[str, Any]]:
        """
        Scans for disks with state 'Unattached'.
        
        Args:
            client: An authenticated ComputeManagementClient instance (async).
        """
        zombies = []
        try:
            # list() returns an AsyncItemPaged, so we use async for
            async for disk in client.disks.list():
                # Filter by region if specified
                if region and disk.location.lower() != region.lower():
                    continue

                if disk.disk_state.lower() == "unattached":
                    # Estimate monthly cost
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
                        "created_at": disk.time_created.isoformat() if disk.time_created else None
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
