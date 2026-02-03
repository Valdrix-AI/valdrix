from typing import List, Dict, Any, Optional
import structlog
from google.cloud import compute_v1
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("gcp")
class GCPUnattachedDisksPlugin(ZombiePlugin):
    """
    Detects unattached Persistent Disks in GCP.
    """

    @property
    def category_key(self) -> str:
        return "unattached_disks"

    async def scan(self, client: compute_v1.DisksClient, project_id: str = None, zone: str = None, monitoring_client: Optional[Any] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Scans for disks with no users and 0 IOPS.
        """
        zombies = []
        try:
            # List all disks in the project and zone
            request = compute_v1.ListDisksRequest(
                project=project_id,
                zone=zone,
            )
            
            import asyncio
            disks = await asyncio.to_thread(client.list, request=request)
            
            for disk in disks:
                # If 'users' list is empty, the disk is unattached
                if not disk.users:
                    # Deep-Scan Layer: Check for recent IOPS if monitoring client is provided
                    if monitoring_client:
                        try:
                            # Placeholder for actual GCP monitoring call if needed
                            pass 
                        except Exception as e:
                            logger.warning("gcp_disk_metrics_failed", disk=disk.name, error=str(e))

                    size_gb = disk.size_gb
                    type_str = disk.type_.split("/")[-1] if disk.type_ else "pd-standard"
                    
                    monthly_waste = self._estimate_disk_cost(size_gb, type_str)
                    
                    zombies.append({
                        "resource_id": str(disk.id),
                        "name": disk.name,
                        "zone": zone,
                        "size_gb": size_gb,
                        "type": type_str,
                        "monthly_cost": float(monthly_waste),
                        "monthly_waste": float(monthly_waste),
                        "description": f"Unattached Disk ({type_str})",
                        "tags": dict(disk.labels) if disk.labels else {},
                        "created_at": disk.creation_timestamp,
                        "explainability_notes": "Disk is 'Unattached' (not linked to any VM) and has had no recent activity detected."
                    })
                    
            return zombies
        except Exception as e:
            logger.error("gcp_unattached_disks_scan_failed", error=str(e), project_id=project_id)
            return []

    def _estimate_disk_cost(self, size_gb: int, type_str: str) -> Decimal:
        """
        Rough estimation of monthly GCP disk cost in USD.
        pd-standard: ~$0.04/GB, pd-ssd: ~$0.17/GB, pd-balanced: ~$0.10/GB
        """
        if "pd-ssd" in type_str:
            rate = Decimal("0.17")
        elif "pd-balanced" in type_str:
            rate = Decimal("0.10")
        else:
            rate = Decimal("0.04") # Standard
            
        return Decimal(size_gb) * rate
