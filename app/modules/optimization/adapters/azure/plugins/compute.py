"""
Azure Compute Plugins - Zero-Cost Zombie Detection.

Detects idle VMs using Cost Management export data.
"""
from typing import List, Dict, Any
from azure.mgmt.compute.aio import ComputeManagementClient
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("azure")
class IdleVmsPlugin(ZombiePlugin):
    """Detect idle Azure VMs via cost export data."""
    
    @property
    def category_key(self) -> str:
        return "idle_azure_vms"
    
    async def scan(self, subscription_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Scan for idle Azure VMs.
        
        Uses cost_records from Cost Management export for zero-cost detection.
        Falls back to Resource Graph if cost data unavailable.
        """
        cost_records = kwargs.get("cost_records")
        
        # Cost-First: Use cost export data
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer
            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_idle_vms(days=7)
        
        # Fallback: Use Resource Graph to identify GPU VMs for review
        zombies = []
        try:
            client = ComputeManagementClient(credentials, subscription_id)
            
            async for vm in client.virtual_machines.list_all():
                # Check for GPU VMs (NC, ND, NV series)
                vm_size = vm.hardware_profile.vm_size.lower()
                is_gpu = any(series in vm_size for series in ["standard_nc", "standard_nd", "standard_nv"])
                
                if is_gpu and vm.instance_view and vm.instance_view.statuses:
                    power_state = next(
                        (s.code for s in vm.instance_view.statuses if s.code.startswith("PowerState/")),
                        None
                    )
                    
                    if power_state == "PowerState/running":
                        zombies.append({
                            "resource_id": vm.id,
                            "resource_name": vm.name,
                            "resource_type": "Virtual Machine (GPU)",
                            "location": vm.location,
                            "vm_size": vm.hardware_profile.vm_size,
                            "recommendation": "Review GPU VM utilization",
                            "action": "review_vm",
                            "confidence_score": 0.60,
                            "explainability_notes": "GPU VM flagged for utilization review. Enable Cost Export for accurate idle detection."
                        })
        except Exception as e:
            logger.warning("azure_vm_scan_error", error=str(e))
        
        return zombies


@registry.register("azure")
class IdleGpuVmsPlugin(ZombiePlugin):
    """High-priority plugin specifically for GPU VMs."""
    
    @property
    def category_key(self) -> str:
        return "idle_azure_gpu_vms"
    
    async def scan(self, subscription_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for idle GPU VMs."""
        cost_records = kwargs.get("cost_records")
        
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer
            analyzer = AzureUsageAnalyzer(cost_records)
            all_vms = analyzer.find_idle_vms(days=7)
            # Filter to GPU only
            return [vm for vm in all_vms if "GPU" in vm.get("resource_type", "")]
        
        return []
