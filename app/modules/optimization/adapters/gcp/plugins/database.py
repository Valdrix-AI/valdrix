"""
GCP Database Plugins - Zero-Cost Zombie Detection.

Detects idle Cloud SQL instances using billing export data.
"""
from typing import List, Dict, Any
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("gcp")
class IdleCloudSqlPlugin(ZombiePlugin):
    """Detect idle Cloud SQL instances."""
    
    @property
    def category_key(self) -> str:
        return "idle_gcp_cloud_sql"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for idle Cloud SQL instances via billing data."""
        billing_records = kwargs.get("billing_records")
        
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_idle_cloud_sql(days=7)
        
        # Fallback: List instances and flag for review
        zombies = []
        try:
            from google.cloud import sqladmin_v1
            client = sqladmin_v1.SqlInstancesServiceClient(credentials=credentials)
            
            request = sqladmin_v1.SqlInstancesListRequest(project=project_id)
            response = client.list(request=request)

            for instance in (getattr(response, "items", None) or []):
                if getattr(instance, "state", None) == "RUNNABLE":
                    settings = getattr(instance, "settings", None)
                    # Flag running instances for review since we don't have connection metrics
                    zombies.append({
                        "resource_id": f"projects/{project_id}/instances/{getattr(instance, 'name', None)}",
                        "resource_name": getattr(instance, "name", None),
                        "resource_type": "Cloud SQL",
                        "tier": getattr(settings, "tier", None),
                        "database_version": getattr(instance, "database_version", None),
                        "recommendation": "Enable billing export for idle detection",
                        "action": "review_sql",
                        "confidence_score": 0.40,
                        "explainability_notes": "Cloud SQL instance flagged for review. Enable billing export for accurate idle detection."
                    })
        except Exception as e:
            logger.warning("gcp_sql_scan_error", error=str(e))
        
        return zombies
