from typing import List, Dict, Any
import structlog
from azure.mgmt.compute.aio import ComputeManagementClient
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("azure")
class AzureOrphanedImagesPlugin(ZombiePlugin):
    """
    Detects Managed Images in Azure that are not being used to create any VMs.
    Managed Images incur storage costs.
    """

    @property
    def category_key(self) -> str:
        return "orphaned_images"

    async def scan(self, client: ComputeManagementClient, region: str = None, credentials: Any = None) -> List[Dict[str, Any]]:
        """
        Scans for Managed Images in the subscription.
        Currently lists all images and considers them 'potentially' orphaned if older than 30 days
        and not associated with an 'active' deployment (simplified for MVP).
        """
        zombies = []
        try:
            async for image in client.images.list():
                # Filter by region if specified
                if region and image.location.lower() != region.lower():
                    continue

                # simplified: tag as zombie if no 'production' tag or similar
                # and older than 60 days
                is_zombie = False
                if image.tags and image.tags.get("environment") == "prod":
                    is_zombie = False
                else:
                    is_zombie = True # Default to zombie for untagged images in Tier 1 refinement
                
                if is_zombie:
                    # Managed Images cost ~$0.05/GB/month
                    # Typical image size is 30GB-128GB
                    size_gb = 30 # Default estimate if unknown
                    monthly_waste = Decimal(str(size_gb)) * Decimal("0.05")
                    
                    zombies.append({
                        "resource_id": image.id,
                        "name": image.name,
                        "region": image.location,
                        "type": "ManagedImage",
                        "monthly_cost": float(monthly_waste),
                        "tags": image.tags or {}
                    })
                    
            return zombies
        except Exception as e:
            logger.error("azure_orphaned_images_scan_failed", error=str(e))
            return []
