"""
Azure Compute Plugins - Zero-Cost Zombie Detection.

Detects idle VMs using Cost Management export data.
"""

from typing import List, Dict, Any
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential
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

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Scan for idle Azure VMs.

        Uses cost_records from Cost Management export for zero-cost detection.
        Falls back to Resource Graph if cost data unavailable.
        """
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        cost_records = kwargs.get("cost_records")

        # Cost-First: Use cost export data
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_idle_vms(days=7)

        # Fallback: Use Resource Graph to identify GPU VMs for review
        zombies = []
        try:
            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = ComputeManagementClient(az_creds, subscription_id)

            async for vm in client.virtual_machines.list_all():
                # Check for GPU VMs (NC, ND, NV series)
                vm_size_raw = getattr(
                    getattr(vm, "hardware_profile", None), "vm_size", None
                )
                if not vm_size_raw:
                    continue
                vm_size = vm_size_raw.lower()
                is_gpu = any(
                    series in vm_size
                    for series in ["standard_nc", "standard_nd", "standard_nv"]
                )

                if is_gpu and vm.instance_view and vm.instance_view.statuses:
                    power_state = next(
                        (
                            s.code
                            for s in vm.instance_view.statuses
                            if s.code and s.code.startswith("PowerState/")
                        ),
                        None,
                    )

                    if power_state == "PowerState/running":
                        zombies.append(
                            {
                                "resource_id": vm.id,
                                "resource_name": vm.name,
                                "resource_type": "Virtual Machine (GPU)",
                                "location": vm.location,
                                "vm_size": vm_size_raw,
                                "recommendation": "Review GPU VM utilization",
                                "action": "review_vm",
                                "confidence_score": 0.60,
                                "explainability_notes": "GPU VM flagged for utilization review. Enable Cost Export for accurate idle detection.",
                            }
                        )
        except Exception as e:
            logger.warning("azure_vm_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class IdleGpuVmsPlugin(ZombiePlugin):
    """High-priority plugin specifically for GPU VMs."""

    @property
    def category_key(self) -> str:
        return "idle_azure_gpu_vms"

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for idle GPU VMs."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        cost_records = kwargs.get("cost_records")

        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            all_vms = analyzer.find_idle_vms(days=7)
            # Filter to GPU only
            return [vm for vm in all_vms if "GPU" in vm.get("resource_type", "")]

        return []


@registry.register("azure")
class StoppedVmsPlugin(ZombiePlugin):
    """Detect Stopped/Deallocated VMs that still incur storage costs."""

    @property
    def category_key(self) -> str:
        return "stopped_azure_vms"

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for stopped VMs."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            return []

        zombies = []
        try:
            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = ComputeManagementClient(az_creds, subscription_id)

            async for vm in client.virtual_machines.list_all():
                # Check Power State
                power_state = None
                if vm.instance_view and vm.instance_view.statuses:
                    power_state = next(
                        (
                            s.code
                            for s in vm.instance_view.statuses
                            if s.code and s.code.startswith("PowerState/")
                        ),
                        None,
                    )

                if power_state in ["PowerState/deallocated", "PowerState/stopped"]:
                    # Get disk costs
                    os_disk_size = (
                        vm.storage_profile.os_disk.disk_size_gb or 30
                        if vm.storage_profile and vm.storage_profile.os_disk
                        else 0
                    )
                    # Rough estimate: $0.05/GB (Standard SSD/HDD mix)
                    monthly_cost = os_disk_size * 0.05
                    zombies.append(
                        {
                            "resource_id": vm.id,
                            "resource_name": vm.name,
                            "resource_type": "Virtual Machine (Stopped)",
                            "location": vm.location,
                            "status": power_state,
                            "monthly_cost": round(monthly_cost, 2),
                            "recommendation": "Delete VM and Disks if decommissioned",
                            "action": "delete_vm",
                            "confidence_score": 1.0,  # 100% sure it's stopped
                            "explainability_notes": f"VM is {power_state}. You are still paying ~${round(monthly_cost, 2)}/mo for its attached disks.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_stopped_vm_scan_error", error=str(e))

        return zombies
