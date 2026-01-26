from typing import List, Dict, Any
import structlog
from azure.mgmt.network import NetworkManagementClient
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("azure")
class AzureOrphanedIpsPlugin(ZombiePlugin):
    """
    Detects Public IP Addresses in Azure that are not associated with any resource.
    """

    @property
    def category_key(self) -> str:
        return "orphaned_ips"

    async def scan(self, client: NetworkManagementClient, region: str = None, credentials: Any = None) -> List[Dict[str, Any]]:
        """
        Scans for Public IPs with no ip_configuration.
        """
        zombies = []
        try:
            # list_all() returns an AsyncItemPaged, so we use async for
            async for ip in client.public_ip_addresses.list_all():
                # Filter by region if specified
                if region and ip.location.lower() != region.lower():
                    continue

                if not ip.ip_configuration:
                    # Unassociated static Public IP costs ~$3.65/month (standard)
                    monthly_waste = Decimal("3.65")
                    
                    zombies.append({
                        "resource_id": ip.id,
                        "name": ip.name,
                        "region": ip.location,
                        "ip_address": ip.ip_address,
                        "sku": ip.sku.name if ip.sku else "Basic",
                        "monthly_cost": float(monthly_waste),
                        "monthly_waste": float(monthly_waste),
                        "tags": ip.tags or {}
                    })
                    
            return zombies
        except Exception as e:
            logger.error("azure_orphaned_ips_scan_failed", error=str(e))
            return []
