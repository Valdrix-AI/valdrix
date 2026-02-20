from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.cloud_api_budget import (
    allow_expensive_cloud_api_call,
)
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("azure")
class OverprovisionedVmPlugin(ZombiePlugin):
    """
    Detects Active Azure VMs that are significantly overprovisioned.
    Criteria: 
    - PowerState: Running
    - Max 'Percentage CPU' < 10% over 7 days
    """
    @property
    def category_key(self) -> str:
        return "overprovisioned_azure_vms"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, str] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        subscription_id = session
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

            compute_client = ComputeManagementClient(az_creds, subscription_id)
            monitor_client = MonitorManagementClient(az_creds, subscription_id)
            
            vms = compute_client.virtual_machines.list_all()

            for vm in vms:
                try:
                    resource_id = str(vm.id or "")
                    if not resource_id:
                        continue
                    
                    rg_name = resource_id.split("/")[4]
                    instance_view = compute_client.virtual_machines.instance_view(
                        resource_group_name=rg_name,
                        vm_name=str(vm.name or "")
                    )
                    is_running = False
                    if instance_view and instance_view.statuses:
                        for status in instance_view.statuses:
                            if status.code == "PowerState/running":
                                is_running = True
                                break
                    
                    if not is_running:
                        continue
                except Exception:
                    continue

                if vm.hardware_profile and vm.hardware_profile.vm_size:
                    size = vm.hardware_profile.vm_size.lower()
                    if "standard_b" in size or "basic_a" in size:
                        continue

                # Get Metrics
                now = datetime.now(timezone.utc)
                start_time = now - timedelta(days=7)
                timespan = f"{start_time.isoformat()}/{now.isoformat()}"
                
                # "Percentage CPU"
                allowed = await allow_expensive_cloud_api_call(
                    "azure_monitor",
                    operation="metrics.list",
                )
                if not allowed:
                    logger.warning(
                        "azure_monitor_budget_exhausted",
                        plugin=self.category_key,
                        vm_name=vm.name,
                    )
                    continue

                metrics_data = monitor_client.metrics.list(
                    resource_uri=str(vm.id or ""),
                    timespan=timespan,
                    interval="P1D", # Daily resolution
                    metricnames="Percentage CPU",
                    aggregation="Maximum"
                )
                
                max_cpu_observed = 0.0
                has_data = False
                below_threshold = True
                threshold = 10.0
                
                if metrics_data.value:
                    for metric in metrics_data.value:
                        if metric.name.value == "Percentage CPU":
                            for ts in metric.timeseries:
                                if ts.data:
                                    for point in ts.data:
                                        if point.maximum is not None:
                                            has_data = True
                                            if point.maximum > max_cpu_observed:
                                                max_cpu_observed = point.maximum
                                            if point.maximum >= threshold:
                                                below_threshold = False
                
                if has_data and below_threshold:
                    monthly_cost = 0.0 # Placeholder
                    
                    vm_size = vm.hardware_profile.vm_size if vm.hardware_profile else "unknown"
                    zombies.append({
                        "resource_id": vm.id,
                        "resource_type": "Azure Virtual Machine",
                        "resource_name": vm.name,
                        "region": vm.location,
                        "monthly_cost": monthly_cost,
                        "recommendation": f"Resize {vm_size} (Max CPU {max_cpu_observed:.1f}%)",
                        "action": "resize_azure_vm",
                        # Fact-based confidence input
                        "utilization_percent": max_cpu_observed,
                        "confidence_score": 0.85,
                        "explainability_notes": f"VM {vm.name} had Max CPU of {max_cpu_observed:.1f}% over the last 7 days."
                    })

        except Exception as e:
            logger.error("azure_rightsizing_scan_error", error=str(e))

        return zombies
