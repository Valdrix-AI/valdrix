"""
GCP Storage Plugins - Zero-Cost Zombie Detection.

Detects unattached disks and old snapshots using Cloud Asset Inventory.
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from google.cloud import compute_v1
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("gcp")
class UnattachedDisksPlugin(ZombiePlugin):
    """Detect unattached Persistent Disks."""
    
    @property
    def category_key(self) -> str:
        return "unattached_gcp_disks"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for unattached disks using Compute API (free)."""
        zombies = []
        
        billing_records = kwargs.get("billing_records")
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_unattached_disks()
        
        try:
            client = compute_v1.DisksClient(credentials=credentials)
            request = compute_v1.AggregatedListDisksRequest(project=project_id)
            
            for zone, response in client.aggregated_list(request=request):
                if not response.disks:
                    continue
                
                for disk in response.disks:
                    # Unattached disk has no users
                    if not disk.users:
                        zone_name = zone.split("/")[-1]
                        size_gb = disk.size_gb
                        # Estimate cost: ~$0.04/GB/month for standard PD
                        estimated_cost = size_gb * 0.04
                        
                        zombies.append({
                            "resource_id": f"projects/{project_id}/zones/{zone_name}/disks/{disk.name}",
                            "resource_name": disk.name,
                            "resource_type": "Persistent Disk",
                            "zone": zone_name,
                            "size_gb": size_gb,
                            "disk_type": disk.type_.split("/")[-1] if disk.type_ else "unknown",
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Snapshot and delete if not needed",
                            "action": "delete_disk",
                            "supports_backup": True,
                            "confidence_score": 0.95,
                            "explainability_notes": f"Disk is not attached to any VM. Size: {size_gb} GB."
                        })
        except Exception as e:
            logger.warning("gcp_disk_scan_error", error=str(e))
        
        return zombies


@registry.register("gcp")
class OldSnapshotsPlugin(ZombiePlugin):
    """Detect old disk snapshots."""
    
    @property
    def category_key(self) -> str:
        return "old_gcp_snapshots"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for snapshots older than retention period."""
        zombies = []
        age_days = kwargs.get("age_days", 90)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=age_days)
        
        try:
            client = compute_v1.SnapshotsClient(credentials=credentials)
            request = compute_v1.ListSnapshotsRequest(project=project_id)
            
            for snapshot in client.list(request=request):
                creation_time = datetime.fromisoformat(snapshot.creation_timestamp.replace("Z", "+00:00"))
                
                if creation_time < cutoff_date:
                    size_gb = snapshot.disk_size_gb
                    # Estimate cost: ~$0.026/GB/month for snapshots
                    estimated_cost = size_gb * 0.026
                    age = (datetime.now(timezone.utc) - creation_time).days
                    
                    zombies.append({
                        "resource_id": f"projects/{project_id}/global/snapshots/{snapshot.name}",
                        "resource_name": snapshot.name,
                        "resource_type": "Disk Snapshot",
                        "size_gb": size_gb,
                        "age_days": age,
                        "monthly_cost": round(estimated_cost, 2),
                        "recommendation": "Delete if no longer needed for recovery",
                        "action": "delete_snapshot",
                        "confidence_score": 0.75,
                        "explainability_notes": f"Snapshot is {age} days old. Review retention policy."
                    })
        except Exception as e:
            logger.warning("gcp_snapshot_scan_error", error=str(e))
        
        return zombies
