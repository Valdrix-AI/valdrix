from typing import List, Dict, Any
import structlog
from google.cloud import compute_v1
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("gcp")
class GCPMachineImagesPlugin(ZombiePlugin):
    """
    Detects Machine Images in GCP.
    These images incur storage costs and often accumulate over time.
    """

    @property
    def category_key(self) -> str:
        return "orphaned_images"

    async def scan(self, client: compute_v1.MachineImagesClient, project_id: str = None, region: str = None) -> List[Dict[str, Any]]:
        """
        Scans for Machine Images in the project.
        """
        zombies = []
        try:
            request = compute_v1.ListMachineImagesRequest(
                project=project_id,
            )
            
            import asyncio
            images = await asyncio.to_thread(client.list, request=request)
            
            for image in images:
                # tagging logic: older than 90 days or lack specific labels
                # for MVP, we report all images that are not "protected"
                if not image.labels or "protected" not in image.labels:
                    # Machine Images cost ~$0.05/GB
                    # simplified estimate of 30GB per image
                    monthly_waste = Decimal("1.50")
                    
                    zombies.append({
                        "resource_id": str(image.id),
                        "name": image.name,
                        "storage_locations": list(image.storage_locations),
                        "monthly_waste": float(monthly_waste),
                        "tags": dict(image.labels) if image.labels else {},
                        "created_at": image.creation_timestamp
                    })
                    
            return zombies
        except Exception as e:
            logger.error("gcp_machine_images_scan_failed", error=str(e), project_id=project_id)
            return []
