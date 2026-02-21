from typing import List, Dict, Any
from datetime import datetime, timezone
from google.cloud import compute_v1
from google.cloud import monitoring_v3
from google.auth.credentials import Credentials as GoogleCredentials
from google.oauth2 import service_account
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.cloud_api_budget import (
    allow_expensive_cloud_api_call,
)
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()


def _resolve_gcp_credentials(credentials: Any) -> Any:
    if credentials is None:
        return None
    if isinstance(credentials, dict):
        return service_account.Credentials.from_service_account_info(credentials)  # type: ignore[no-untyped-call]
    if isinstance(credentials, GoogleCredentials):
        return credentials
    # Allow already-instantiated credential-like objects (used in tests and adapters).
    return credentials

@registry.register("gcp")
class OverprovisionedComputePlugin(ZombiePlugin):
    """
    Detects Active GCP Compute Instances that are significantly overprovisioned.
    Criteria: 
    - Status: RUNNING
    - Max 'compute.googleapis.com/instance/cpu/utilization' < 10% (0.1) over 7 days
    """
    @property
    def category_key(self) -> str:
        return "overprovisioned_gcp_instances"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        project_id = session
        zombies = []
        
        try:
            gcp_creds = _resolve_gcp_credentials(credentials)
            
            # 1. List Instances (Aggregated List for all zones)
            instances_client = compute_v1.InstancesClient(credentials=gcp_creds)
            agg_list = instances_client.aggregated_list(project=project_id)

            monitor_client = monitoring_v3.MetricServiceClient(credentials=gcp_creds)
            project_name = f"projects/{project_id}"

            for zone_path, page in agg_list:
                if not page.instances:
                    continue
                
                for instance in page.instances:
                    if instance.status != "RUNNING":
                        continue
                    
                    # Skip insignificant types (e.g. e2-micro, f1-micro)
                    machine_type_url = instance.machine_type
                    if "micro" in machine_type_url or "small" in machine_type_url:
                        continue
                        
                    instance_id = str(instance.id)

                    # 2. Check Metrics
                    # Filter: resource.type="gce_instance" AND resource.labels.instance_id="{instance_id}"
                    # Metric: compute.googleapis.com/instance/cpu/utilization
                    
                    filter_str = (
                        f'metric.type="compute.googleapis.com/instance/cpu/utilization" '
                        f'AND resource.labels.instance_id="{instance_id}"'
                    )
                    
                    now = datetime.now(timezone.utc)
                    start_time = now.timestamp() - (7 * 86400)
                    end_time = now.timestamp()
                    
                    interval = monitoring_v3.TimeInterval(
                        {"start_time": {"seconds": int(start_time)}, "end_time": {"seconds": int(end_time)}}
                    )
                    
                    aggregation = monitoring_v3.Aggregation(
                        {
                            "alignment_period": {"seconds": 86400}, # Daily
                            "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_MAX,
                        }
                    )

                    allowed = await allow_expensive_cloud_api_call(
                        "gcp_monitoring",
                        operation="list_time_series",
                    )
                    if not allowed:
                        logger.warning(
                            "gcp_monitoring_budget_exhausted",
                            plugin=self.category_key,
                            instance_id=instance_id,
                        )
                        continue

                    results = monitor_client.list_time_series(
                        request={
                            "name": project_name,
                            "filter": filter_str,
                            "interval": interval,
                            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                            "aggregation": aggregation,
                        }
                    )
                    
                    max_cpu_observed = 0.0
                    has_data = False
                    below_threshold = True
                    threshold = 0.1 # 10%
                    
                    for result in results:
                        for point in result.points:
                            val = point.value.double_value
                            has_data = True
                            if val > max_cpu_observed:
                                max_cpu_observed = val
                            if val >= threshold:
                                below_threshold = False
                                break
                    
                    if has_data and below_threshold:
                        # Convert 0.05 -> 5.0%
                        max_cpu_percent = max_cpu_observed * 100.0
                        monthly_cost = 0.0 # Placeholder
                        
                        machine_type_name = machine_type_url.split("/")[-1]

                        zombies.append({
                            "resource_id": instance_id,
                            "resource_type": "GCP Compute Instance",
                            "resource_name": instance.name,
                            "region": instance.zone, # Full URL usually, simplified
                            "monthly_cost": monthly_cost,
                            "recommendation": f"Resize {machine_type_name} (Max CPU {max_cpu_percent:.1f}%)",
                            "action": "resize_gcp_instance",
                            # Fact-based confidence input
                            "utilization_percent": max_cpu_percent,
                            "confidence_score": 0.85,
                            "explainability_notes": f"Instance {machine_type_name} had Max CPU of {max_cpu_percent:.1f}% over the last 7 days."
                        })

        except Exception as e:
            logger.error("gcp_rightsizing_scan_error", error=str(e))

        return zombies
