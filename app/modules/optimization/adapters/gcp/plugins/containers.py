"""
GCP Container Plugins - Zero-Cost Zombie Detection.

Detects empty GKE clusters and idle Cloud Run services.
"""
from typing import List, Dict, Any
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("gcp")
class EmptyGkeClusterPlugin(ZombiePlugin):
    """Detect GKE clusters with no workloads."""
    
    @property
    def category_key(self) -> str:
        return "empty_gke_clusters"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for GKE clusters with control plane costs but no nodes."""
        billing_records = kwargs.get("billing_records")
        
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_empty_gke_clusters(days=7)
        
        # Fallback: Check for clusters with 0 nodes
        zombies = []
        try:
            from google.cloud import container_v1
            client = container_v1.ClusterManagerClient(credentials=credentials)
            
            parent = f"projects/{project_id}/locations/-"
            response = client.list_clusters(parent=parent)

            for cluster in (getattr(response, "clusters", None) or []):
                node_pools = getattr(cluster, "node_pools", None) or []
                total_nodes = sum((getattr(np, "initial_node_count", 0) or 0) for np in node_pools)
                
                if total_nodes == 0:
                    # GKE control plane: ~$73/month for Autopilot or first zonal cluster
                    estimated_cost = 73.0
                    resource_id = getattr(cluster, "self_link", None) or getattr(cluster, "name", None)

                    zombies.append({
                        "resource_id": resource_id,
                        "resource_name": getattr(cluster, "name", None),
                        "resource_type": "GKE Cluster",
                        "location": getattr(cluster, "location", None),
                        "node_count": 0,
                        "monthly_cost": round(estimated_cost, 2),
                        "recommendation": "Delete empty cluster",
                        "action": "delete_gke_cluster",
                        "confidence_score": 0.92,
                        "explainability_notes": "GKE cluster has no nodes configured, only control plane cost."
                    })
        except Exception as e:
            logger.warning("gcp_gke_scan_error", error=str(e))
        
        return zombies


@registry.register("gcp")
class IdleCloudRunPlugin(ZombiePlugin):
    """Detect Cloud Run services with zero requests."""
    
    @property
    def category_key(self) -> str:
        return "idle_cloud_run"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for Cloud Run services with no traffic."""
        billing_records = kwargs.get("billing_records")
        
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_idle_cloud_run(days=30)
        
        # Cloud Run is pay-per-request, so without billing data we can't detect idle
        return []


@registry.register("gcp")
class IdleCloudFunctionsPlugin(ZombiePlugin):
    """Detect Cloud Functions with zero invocations."""
    
    @property
    def category_key(self) -> str:
        return "idle_cloud_functions"
    
    async def scan(self, project_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for Cloud Functions with no invocations."""
        billing_records = kwargs.get("billing_records")
        
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer
            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_idle_cloud_functions(days=30)
        
        # Cloud Functions is pay-per-invocation, so without billing data we can't detect idle
        return []
