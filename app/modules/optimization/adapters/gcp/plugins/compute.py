"""
GCP Compute Plugins - Zero-Cost Zombie Detection.

Detects idle VMs and GPU instances using BigQuery billing export data.
"""
from typing import List, Dict, Any
from google.cloud import compute_v1
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("gcp")
class IdleVmsPlugin(ZombiePlugin):
    """Detect idle Compute Engine VMs via billing data."""
    
    @property
    def category_key(self) -> str:
        return "idle_gcp_vms"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Scan for idle GCP VMs.
        
        Uses billing_records from BigQuery export for zero-cost detection.
        Falls back to Cloud Asset Inventory if billing data unavailable.
        """
        billing_records = kwargs.get("billing_records")
        
        # CUR-First: Use billing export data
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_idle_vms(days=7)
        
        # Fallback: Use Cloud Asset Inventory + basic heuristics
        zombies = []
        try:
            client = compute_v1.InstancesClient(credentials=credentials)
            request = compute_v1.AggregatedListInstancesRequest(project=project_id)
            
            for zone, response in client.aggregated_list(request=request):
                if not response.instances:
                    continue
                
                for instance in response.instances:
                    if instance.status != "RUNNING":
                        continue
                    
                    # Check for GPU instances (high value targets)
                    is_gpu = bool(instance.guest_accelerators) or "a2-" in instance.machine_type or "g2-" in instance.machine_type
                    
                    # Without metrics, flag GPU instances for review
                    if is_gpu:
                        zone_name = zone.split("/")[-1]
                        zombies.append({
                            "resource_id": f"projects/{project_id}/zones/{zone_name}/instances/{instance.name}",
                            "resource_name": instance.name,
                            "resource_type": "Compute Engine VM (GPU)",
                            "zone": zone_name,
                            "machine_type": instance.machine_type.split("/")[-1],
                            "recommendation": "Review GPU instance utilization",
                            "action": "review_vm",
                            "confidence_score": 0.60,
                            "explainability_notes": "GPU instance flagged for utilization review. Enable billing export for accurate idle detection."
                        })
        except Exception as e:
            logger.warning("gcp_vm_scan_error", error=str(e))
        
        return zombies


@registry.register("gcp")
class IdleGpuInstancesPlugin(ZombiePlugin):
    """High-priority plugin specifically for GPU instances."""
    
    @property
    def category_key(self) -> str:
        return "idle_gcp_gpu_instances"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for idle GPU instances."""
        billing_records = kwargs.get("billing_records")
        
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            all_vms = analyzer.find_idle_vms(days=7)
            # Filter to GPU only
            return [vm for vm in all_vms if "GPU" in vm.get("resource_type", "")]
        
        # Fallback handled by IdleVmsPlugin
        return []
