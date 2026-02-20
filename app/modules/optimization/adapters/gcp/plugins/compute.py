"""
GCP Compute Plugins - Zero-Cost Zombie Detection.

Detects idle VMs and GPU instances using BigQuery billing export data.
"""

from typing import List, Dict, Any
from google.cloud import compute_v1
from google.oauth2 import service_account
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

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Scan for idle GCP VMs.

        Uses billing_records from BigQuery export for zero-cost detection.
        Falls back to Cloud Asset Inventory if billing data unavailable.
        """
        project_id = str(kwargs.get("project_id") or session or "")
        if not project_id:
            logger.warning("gcp_scan_missing_project_id", plugin=self.category_key)
            return []

        billing_records = kwargs.get("billing_records")

        # CUR-First: Use billing export data
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer

            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_idle_vms(days=7)

        # Fallback: Use Cloud Asset Inventory + basic heuristics
        zombies = []
        print(f"DEBUG: Entering fallback for {project_id}")
        try:
            gcp_creds = None
            if credentials:
                gcp_creds = service_account.Credentials.from_service_account_info(credentials)  # type: ignore[no-untyped-call]
            print("DEBUG: Instantiating InstancesClient")
            client = compute_v1.InstancesClient(credentials=gcp_creds)
            print(f"DEBUG: Creating request for project {project_id}")
            try:
                request = compute_v1.AggregatedListInstancesRequest(project=project_id)
            except AttributeError:
                print("DEBUG: AggregatedListInstancesRequest not found in compute_v1")
                # Fallback to simple dict if needed, or check types
                request = {"project": project_id} 
            
            print(f"DEBUG: Calling aggregated_list with request {request}")
            for zone, response in client.aggregated_list(request=request):
                if not response.instances:
                    continue

                print(f"DEBUG: Processing zone {zone}")
                for instance in response.instances:
                    print(f"DEBUG: Checking instance {instance.name}, status {instance.status}")
                    if instance.status != "RUNNING":
                        continue

                    # Check for GPU instances (high value targets)
                    is_gpu = (
                        bool(instance.guest_accelerators)
                        or "a2-" in instance.machine_type
                        or "g2-" in instance.machine_type
                    )
                    print(f"DEBUG: is_gpu={is_gpu}")

                    # Without metrics, flag GPU instances for review
                    if is_gpu:
                        zone_name = zone.split("/")[-1]
                        zombies.append(
                            {
                                "resource_id": f"projects/{project_id}/zones/{zone_name}/instances/{instance.name}",
                                "resource_name": instance.name,
                                "resource_type": "Compute Engine VM (GPU)",
                                "zone": zone_name,
                                "machine_type": instance.machine_type.split("/")[-1],
                                "recommendation": "Review GPU instance utilization",
                                "action": "review_vm",
                                "confidence_score": 0.60,
                                "explainability_notes": "GPU instance flagged for utilization review. Enable billing export for accurate idle detection.",
                            }
                        )
        except Exception as e:
            logger.warning("gcp_vm_scan_error", error=str(e))

        return zombies


@registry.register("gcp")
class IdleGpuInstancesPlugin(ZombiePlugin):
    """High-priority plugin specifically for GPU instances."""

    @property
    def category_key(self) -> str:
        return "idle_gcp_gpu_instances"

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for idle GPU instances."""
        project_id = str(kwargs.get("project_id") or session or "")
        if not project_id:
            logger.warning("gcp_scan_missing_project_id", plugin=self.category_key)
            return []

        billing_records = kwargs.get("billing_records")

        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer

            analyzer = GCPUsageAnalyzer(billing_records)
            all_vms = analyzer.find_idle_vms(days=7)
            # Filter to GPU only
            return [vm for vm in all_vms if "GPU" in vm.get("resource_type", "")]

        # Fallback handled by IdleVmsPlugin
        return []


@registry.register("gcp")
class StoppedVmsPlugin(ZombiePlugin):
    """Detect Stopped/Terminated Instances that still incur storage costs."""

    @property
    def category_key(self) -> str:
        return "stopped_gcp_instances"

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for stopped instances."""
        project_id = str(kwargs.get("project_id") or session or "")
        if not project_id:
            return []

        zombies = []
        try:
            gcp_creds = None
            if credentials:
                gcp_creds = service_account.Credentials.from_service_account_info(credentials)  # type: ignore[no-untyped-call]
            client = compute_v1.InstancesClient(credentials=gcp_creds)
            request = compute_v1.AggregatedListInstancesRequest(project=project_id)

            for zone, response in client.aggregated_list(request=request):
                if not response.instances:
                    continue

                for instance in response.instances:
                    if instance.status in ["TERMINATED", "STOPPED", "SUSPENDED"]:
                        # Calculate disk costs
                        disk_cost = 0.0
                        disk_details = []
                        for disk in instance.disks:
                            size_gb = disk.disk_size_gb or 30 # Default estimate
                            # ~$0.04/GB for standard pd
                            disk_cost += size_gb * 0.04
                            disk_details.append(f"{size_gb}GB")

                        zombies.append(
                            {
                                "resource_id": f"projects/{project_id}/zones/{zone}/instances/{instance.name}",
                                "resource_name": instance.name,
                                "resource_type": "Compute Instance (Stopped)",
                                "zone": zone.split("/")[-1],
                                "status": instance.status,
                                "monthly_cost": round(disk_cost, 2),
                                "recommendation": "Delete Instance and Disks if decommissioned",
                                "action": "delete_instance",
                                "confidence_score": 1.0,
                                "explainability_notes": f"Instance is {instance.status}. You are paying ~${round(disk_cost, 2)}/mo for attached disks ({', '.join(disk_details)}).",
                            }
                        )
        except Exception as e:
            logger.warning("gcp_stopped_vm_scan_error", error=str(e))

        return zombies
