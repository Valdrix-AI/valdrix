from typing import List, Dict, Any, Optional
import structlog
from google.cloud import compute_v1
from google.cloud import logging as gcp_logging
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
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

                # Deep-Scan Layer: CPU Utilization Check
                cpu_utilization = None
                from google.cloud import monitoring_v3
                from datetime import datetime, timedelta, timezone
                
                # Note: We need a monitoring client. If not passed, we skip metrics but log warning.
                # In production, the orchestrator should pass it.
                monitoring_client = kwargs.get("monitoring_client")
                
                if monitoring_client:
                    try:
                        end_time = datetime.now(timezone.utc)
                        start_time = end_time - timedelta(days=7)
                        
                        interval = monitoring_v3.TimeInterval(
                            start_time=start_time,
                            end_time=end_time
                        )
                        
                        # Filter for specific instance CPU metric
                        filter_str = (
                            f'metric.type="compute.googleapis.com/instance/cpu/utilization" AND '
                            f'resource.labels.instance_id="{inst.id}"'
                        )
                        
                        results = monitoring_client.list_time_series(
                            request={
                                "name": f"projects/{project_id}",
                                "filter": filter_str,
                                "interval": interval,
                                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                            }
                        )
                        
                        data_points = []
                        for result in results:
                            for point in result.points:
                                data_points.append(point.value.double_value)
                        
                        if data_points:
                            cpu_utilization = (sum(data_points) / len(data_points)) * 100 # Convert to percentage
                    except Exception as e:
                        logger.warning("gcp_instance_metrics_failed", instance=inst.name, error=str(e))

                # Filtering Logic: Only consider idle if CPU < 5% (or metrics missing)
                if cpu_utilization is not None and cpu_utilization > 5:
                    continue

                # 1. GPU Signal
                confidence = Decimal("0.8")
                if is_gpu:
                    confidence = Decimal("0.95")

                # 2. Attribution Signal (Audit Logs)
                owner = "unknown"
                if logging_client:
                    owner = await self._get_attribution(logging_client, inst.id, zone_name)

                # 3. Cost Estimation
                monthly_cost = self._estimate_instance_cost(machine_type, is_gpu, region=zone_name)

                zombies.append({
                    "resource_id": str(inst.id),
                    "name": inst.name,
                    "region": zone_name,
                    "type": machine_type,
                    "is_gpu": is_gpu,
                    "owner": owner,
                    "monthly_cost": float(monthly_cost),
                    "monthly_waste": float(monthly_cost),
                    "confidence_score": float(confidence),
                    "tags": dict(inst.labels) if inst.labels else {},
                    "explainability_notes": f"Instance average CPU utilization was {cpu_utilization:.2f}% over the last 7 days." if cpu_utilization is not None else "Instance is running but no utilization data found.",
                    "metadata": {
                        "instance_id": inst.id,
                        "cpu_platform": inst.cpu_platform,
                        "creation_timestamp": inst.creation_timestamp,
                        "cpu_utilization": cpu_utilization
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

    def _estimate_instance_cost(self, machine_type: str, is_gpu: bool, region: str = "us-central1") -> Decimal:
        """Rough estimation of monthly instance cost via PricingService."""
        from app.modules.reporting.domain.pricing.service import PricingService
        
        resource_size = "default"
        if is_gpu:
            resource_size = "gpu"
        elif "n1-standard" in machine_type:
            resource_size = "n1-standard"
        elif "f1-micro" in machine_type or "e2-micro" in machine_type:
            resource_size = "micro"
            
        return Decimal(str(PricingService.estimate_monthly_waste(
            provider="gcp",
            resource_type="instance",
            resource_size=resource_size,
            region=region
        )))
