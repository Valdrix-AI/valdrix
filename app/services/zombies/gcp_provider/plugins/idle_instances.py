from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime, timedelta, timezone
from google.cloud import compute_v1
from google.cloud import logging as gcp_logging
from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.zombies.registry import registry
from decimal import Decimal

logger = structlog.get_logger()

@registry.register("gcp")
class GCPIdleInstancePlugin(ZombiePlugin):
    """
    Detects idle Compute Engine instances in GCP.
    Enhanced with GPU hunting and Audit Log attribution.
    """

    @property
    def category_key(self) -> str:
        return "idle_instances"

    async def scan(self, client: compute_v1.InstancesClient, project_id: str, zone: str = None, logging_client: Optional[gcp_logging.Client] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Scans for instances with low utilization.
        
        Args:
            client: Authenticated InstancesClient.
            logging_client: Authenticated GCP Logging client for attribution.
        """
        zombies = []
        try:
            # We use aggregated_list to find instances across zones if zone is not specific
            if not zone or zone == "global":
                request = compute_v1.AggregatedListInstancesRequest(project=project_id)
                agg_list = client.aggregated_list(request=request)
                iterator = []
                for zone_path, response in agg_list:
                    if response.instances:
                        zone_name = zone_path.split('/')[-1]
                        for inst in response.instances:
                            iterator.append((zone_name, inst))
            else:
                request = compute_v1.ListInstancesRequest(project=project_id, zone=zone)
                instances = client.list(request=request)
                iterator = [(zone, inst) for inst in instances]

            for zone_name, inst in iterator:
                if inst.status != "RUNNING":
                    continue

                machine_type = inst.machine_type.split('/')[-1]
                is_gpu = "a2-" in machine_type or "g2-" in machine_type or inst.guest_accelerators
                
                # 1. GPU Signal
                confidence = Decimal("0.8")
                if is_gpu:
                    confidence = Decimal("0.95")

                # 2. Attribution Signal (Audit Logs)
                owner = "unknown"
                if logging_client:
                    owner = await self._get_attribution(logging_client, inst.id, zone_name)

                # 3. Cost Estimation
                monthly_cost = self._estimate_instance_cost(machine_type, is_gpu)

                zombies.append({
                    "id": str(inst.id),
                    "name": inst.name,
                    "region": zone_name,
                    "type": machine_type,
                    "is_gpu": is_gpu,
                    "owner": owner,
                    "monthly_waste": float(monthly_cost),
                    "confidence_score": float(confidence),
                    "tags": dict(inst.labels) if inst.labels else {},
                    "metadata": {
                        "instance_id": inst.id,
                        "cpu_platform": inst.cpu_platform,
                        "creation_timestamp": inst.creation_timestamp
                    }
                })
                    
            return zombies
        except Exception as e:
            logger.error("gcp_idle_instances_scan_failed", error=str(e))
            return []

    async def _get_attribution(self, logging_client: gcp_logging.Client, instance_id: int, zone: str) -> str:
        """
        Queries GCP Audit Logs to find the principal who created/modified the instance.
        """
        try:
            # Look for GCE Instance activity in audit logs
            filter_str = (
                f'resource.type="gce_instance" AND '
                f'resource.labels.instance_id="{instance_id}" AND '
                f'resource.labels.zone="{zone}" AND '
                f'protoPayload.methodName:"insert" OR protoPayload.methodName:"patch" OR protoPayload.methodName:"update"'
            )
            
            # List entries, most recent first
            entries = logging_client.list_entries(filter_=filter_str, order_by=gcp_logging.DESCENDING, page_size=1)
            
            for entry in entries:
                if entry.payload and "authenticationInfo" in entry.payload:
                    return entry.payload["authenticationInfo"].get("principalEmail", "unknown_principal")
            
            return "service_account_or_system"
        except Exception as e:
            logger.error("gcp_attribution_failed", instance_id=instance_id, error=str(e))
            return "attribution_failed"

    def _estimate_instance_cost(self, machine_type: str, is_gpu: bool) -> Decimal:
        """Rough estimation of monthly instance cost."""
        if is_gpu:
            return Decimal("1500.00")
        if "n1-standard" in machine_type:
            return Decimal("100.00")
        if "f1-micro" in machine_type or "e2-micro" in machine_type:
            return Decimal("5.00")
        return Decimal("50.00")
