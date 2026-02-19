from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("aws")
class IdleOpenSearchPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_opensearch_domains"

    async def scan(
        self,
        session: aioboto3.Session,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,  # Added missing param
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        zombies = []
        
        try:
            async with self._get_client(
                session, "opensearch", region, credentials, config=config
            ) as client, self._get_client(
                session, "cloudwatch", region, credentials, config=config
            ) as cloudwatch:
                
                # 1. List Domains
                response = await client.list_domain_names()
                domain_names = response.get("DomainNames", [])
                
                for domain_entry in domain_names:
                    domain_name = domain_entry["DomainName"]
                    
                    # Get details for ARN/ID
                    desc = await client.describe_domain(DomainName=domain_name)
                    status = desc.get("DomainStatus", {})
                    
                    if status.get("Deleted"):
                        continue
                        
                    arn = status.get("ARN")
                    # Check metrics: SearchableDocuments (data exists?) vs SearchRequestRate (usage?)
                    # If SearchableDocuments > 0 but Requests == 0 -> Zombie/Hoarder
                    
                    now = datetime.now(timezone.utc)
                    start_time = now - timedelta(days=7)
                    end_time = now
                    
                    # Check SearchableDocuments (Average)
                    docs_metric = await cloudwatch.get_metric_statistics(
                        Namespace="AWS/ES",
                        MetricName="SearchableDocuments",
                        Dimensions=[
                            {"Name": "DomainName", "Value": domain_name},
                            {"Name": "ClientId", "Value": status.get("DomainId", "").split("/")[0]} 
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=86400,
                        Statistics=["Average"]
                    )
                    
                    has_data = False
                    if docs_metric.get("Datapoints"):
                        for dp in docs_metric["Datapoints"]:
                            if dp.get("Average", 0) > 0:
                                has_data = True
                                break
                    
                    if not has_data:
                        # If no data, maybe it's just empty? 
                        # Empty is also a zombie but "Idle" implies allocated resources doing nothing.
                        # Let's consider valid use case: setup but forgot to load data?
                        pass

                    # Check SearchRequestRate or similar activity metric
                    # AWS/ES metric: SearchRequestRate (requests per minute?) - verify exact metric name
                    # Or 'CPUUtilization' < 1%?
                    # Let's use SearchRequestRate as proxy for "Search Usage"
                    
                    req_metric = await cloudwatch.get_metric_statistics(
                        Namespace="AWS/ES",
                        MetricName="SearchRequestRate", # Check valid metric for OpenSearch
                        Dimensions=[
                             {"Name": "DomainName", "Value": domain_name},
                             {"Name": "ClientId", "Value": status.get("DomainId", "").split("/")[0]}
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=86400,
                        Statistics=["Sum"]
                    )
                    
                    has_requests = False
                    if req_metric.get("Datapoints"):
                        for dp in req_metric["Datapoints"]:
                            if dp.get("Sum", 0) > 0:
                                has_requests = True
                                break
                                
                    if has_data and not has_requests:
                        # Zombie confirmed: Has data but no searches
                        
                        # Cost Estimate
                        cluster_config = status.get("ClusterConfig", {})
                        count = cluster_config.get("InstanceCount", 1)
                        dedicated_master_enabled = cluster_config.get("DedicatedMasterEnabled", False)
                        
                        # Rough estimate (t3.small.search ~$0.036/hr * 730 * count)
                        # TODO: Use pricing service
                        monthly_cost = 30.0 * count # Placeholder
                        if dedicated_master_enabled:
                            monthly_cost += 50.0 
                            
                        zombies.append({
                            "resource_id": arn,
                            "resource_type": "AWS OpenSearch Domain",
                            "resource_name": domain_name,
                            "region": region,
                            "monthly_cost": monthly_cost,
                            "recommendation": "Snapshot and delete unused OpenSearch domain",
                            "action": "snapshot_and_delete_opensearch",
                            "confidence_score": 0.9,
                            "explainability_notes": f"Domain '{domain_name}' has documents but 0 search requests in last 7 days."
                        })

        except Exception as e:
            logger.error("aws_opensearch_scan_error", error=str(e))
            
        return zombies
