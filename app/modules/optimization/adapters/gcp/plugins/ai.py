from typing import List, Dict, Any
from datetime import datetime, timezone
from google.cloud import aiplatform
from google.cloud import monitoring_v3
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.cloud_api_budget import (
    allow_expensive_cloud_api_call,
)
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("gcp")
class IdleVertexEndpointsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_vertex_ai_endpoints"

    async def scan(
        self,
        session: str,  # acts as project_id for GCP
        credentials: Any,
        region: str = "global",  # Actually specific regions needed, defaulting to scan main ones?
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        project_id = session
        zombies = []
        
        # Vertex AI is regional. We should iterate regions or rely on region passed in scan
        # For simplicity/TDD, we assume 'region' argument is valid or we default to us-central1
        target_region = region if region != "global" else "us-central1"
        
        endpoint_client_options = {"api_endpoint": f"{target_region}-aiplatform.googleapis.com"}
        
        try:
            # 1. List Endpoints
            client = aiplatform.EndpointServiceClient(
                client_options=endpoint_client_options, 
                credentials=credentials
            )
            # Parent format: projects/{project}/locations/{location}
            parent = f"projects/{project_id}/locations/{target_region}"
            
            endpoints = client.list_endpoints(parent=parent)
            
            # 2. Check Metrics for each endpoint
            monitor_client = monitoring_v3.MetricServiceClient(credentials=credentials)
            project_name = f"projects/{project_id}"

            for ep in endpoints:
                # If traffic split is empty object, it might be undeployed already?
                if not ep.traffic_split:
                    continue

                # Metric: aiplatform.googleapis.com/endpoint/prediction_count
                # Filter: resource.type="aiplatform.googleapis.com/Endpoint" AND resource.labels.endpoint_id="{ep.name.split('/')[-1]}"
                ep_id = ep.name.split('/')[-1]
                filter_str = (
                    f'metric.type="aiplatform.googleapis.com/endpoint/prediction_count" '
                    f'AND resource.labels.endpoint_id="{ep_id}"'
                )
                
                now = datetime.now(timezone.utc)
                # 7 days ago
                start_time = now.timestamp() - (7 * 86400)
                end_time = now.timestamp()
                
                interval = monitoring_v3.TimeInterval(
                    {"start_time": {"seconds": int(start_time)}, "end_time": {"seconds": int(end_time)}}
                )
                
                # Check metrics (simplified aggregation)
                allowed = await allow_expensive_cloud_api_call(
                    "gcp_monitoring",
                    operation="list_time_series",
                )
                if not allowed:
                    logger.warning(
                        "gcp_monitoring_budget_exhausted",
                        plugin=self.category_key,
                        endpoint_id=ep_id,
                    )
                    continue

                results = monitor_client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": filter_str,
                        "interval": interval,
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                    }
                )
                
                # If no time series data points = 0 predictions
                has_predictions = False
                for result in results:
                    if result.points:
                        has_predictions = True
                        break
                
                if not has_predictions:
                    # Cost Estimate: ~$0.50 - $5.00/hr depending on machine type
                    # We'd need to inspect DeployedModels to get exact machine type cost
                    monthly_cost = 200.0 # Placeholder average
                    
                    zombies.append({
                        "resource_id": ep.name,
                        "resource_type": "Vertex AI Endpoint",
                        "resource_name": ep.display_name,
                        "region": target_region,
                        "monthly_cost": monthly_cost,
                        "recommendation": "Undeploy models from idle endpoint",
                        "action": "undeploy_vertex_endpoint",
                        "confidence_score": 0.95,
                        "explainability_notes": f"Endpoint '{ep.display_name}' had 0 predictions in the last 7 days."
                    })

        except Exception as e:
            logger.error("gcp_vertex_scan_error", error=str(e))

        return zombies
