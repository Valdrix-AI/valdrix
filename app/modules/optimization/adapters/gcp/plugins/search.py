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
class IdleVectorSearchPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_vector_search_indices"

    async def scan(
        self,
        session: str,
        credentials: Any,
        region: str = "global",
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        project_id = session
        zombies = []
        target_region = region if region != "global" else "us-central1"
        
        endpoint_client_options = {"api_endpoint": f"{target_region}-aiplatform.googleapis.com"}

        try:
            # 1. List Index Endpoints (Vector Search)
            client = aiplatform.IndexEndpointServiceClient(
                client_options=endpoint_client_options, 
                credentials=credentials
            )
            parent = f"projects/{project_id}/locations/{target_region}"
            index_endpoints = client.list_index_endpoints(parent=parent)
            
            monitor_client = monitoring_v3.MetricServiceClient(credentials=credentials)
            project_name = f"projects/{project_id}"

            for ie in index_endpoints:
                # If no deployed indexes, cost is lower (just endpoint node?), but still valid to check
                if not ie.deployed_indexes:
                    continue

                # Metric: aiplatform.googleapis.com/index_endpoint/query_count ?? Verify metric
                # Or request_count
                ie_id = ie.name.split('/')[-1]
                filter_str = (
                    f'metric.type="aiplatform.googleapis.com/index_endpoint/request_count" '
                    f'AND resource.labels.index_endpoint_id="{ie_id}"'
                )
                
                now = datetime.now(timezone.utc)
                start_time = now.timestamp() - (7 * 86400)
                end_time = now.timestamp()
                
                interval = monitoring_v3.TimeInterval(
                    {"start_time": {"seconds": int(start_time)}, "end_time": {"seconds": int(end_time)}}
                )
                
                allowed = await allow_expensive_cloud_api_call(
                    "gcp_monitoring",
                    operation="list_time_series",
                )
                if not allowed:
                    logger.warning(
                        "gcp_monitoring_budget_exhausted",
                        plugin=self.category_key,
                        index_endpoint_id=ie_id,
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
                
                has_queries = False
                for result in results:
                    if result.points:
                        has_queries = True
                        break
                
                if not has_queries:
                    monthly_cost = 500.0 # Vector Search is expensive (node hours)
                    
                    zombies.append({
                        "resource_id": ie.name,
                        "resource_type": "Vertex AI Vector Index",
                        "resource_name": ie.display_name,
                        "region": target_region,
                        "monthly_cost": monthly_cost,
                        "recommendation": "Undeploy unused vector index",
                        "action": "undeploy_vector_index",
                        "confidence_score": 0.95,
                        "explainability_notes": f"Vector Index Endpoint '{ie.display_name}' had 0 queries in the last 7 days."
                    })

        except Exception as e:
            logger.error("gcp_vector_scan_error", error=str(e))

        return zombies
