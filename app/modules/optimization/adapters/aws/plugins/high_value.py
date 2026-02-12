"""
AWS High-Value Zombie Detection Plugins

Detects idle/unused resources in high-cost AWS services:
- EKS Clusters (~$73+/month control plane)
- ElastiCache Clusters ($12-500/month)
- SageMaker Notebooks ($50-500/month)
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()


@registry.register("aws")
class IdleEksPlugin(ZombiePlugin):
    """
    Detects EKS clusters with no running workloads.
    EKS control plane costs $0.10/hour (~$73/month) even when idle.
    """
    
    @property
    def category_key(self) -> str:
        return "idle_eks_clusters"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] | None = None, 
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        zombies = []
        
        # Check for CUR-based detection first
        cur_records = kwargs.get("cur_records")
        if cur_records:
            from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer
            analyzer = CURUsageAnalyzer(cur_records)
            return analyzer.find_idle_eks_clusters()
        
        try:
            async with self._get_client(session, "eks", region, credentials, config=config) as eks:
                paginator = eks.get_paginator("list_clusters")
                async for page in paginator.paginate():
                    for cluster_name in page.get("clusters", []):
                        try:
                            # Get cluster details
                            cluster_info = await eks.describe_cluster(name=cluster_name)
                            cluster = cluster_info.get("cluster", {})
                            
                            # Check node groups
                            ng_paginator = eks.get_paginator("list_nodegroups")
                            total_nodes = 0
                            async for ng_page in ng_paginator.paginate(clusterName=cluster_name):
                                for ng_name in ng_page.get("nodegroups", []):
                                    ng_info = await eks.describe_nodegroup(
                                        clusterName=cluster_name,
                                        nodegroupName=ng_name
                                    )
                                    ng = ng_info.get("nodegroup", {})
                                    scaling = ng.get("scalingConfig", {})
                                    total_nodes += scaling.get("desiredSize", 0)
                            
                            # Cluster with 0 nodes is definitely idle
                            if total_nodes == 0:
                                zombies.append({
                                    "resource_id": cluster_name,
                                    "resource_type": "EKS Cluster",
                                    "cluster_arn": cluster.get("arn", ""),
                                    "node_count": 0,
                                    "monthly_cost": 73.00,  # Base control plane cost
                                    "recommendation": "EKS cluster has no nodes. Delete if not needed.",
                                    "action": "delete_eks_cluster",
                                    "confidence_score": 0.95,
                                    "explainability_notes": "EKS cluster is paying for control plane but has zero nodes attached.",
                                    "detection_method": "api-scan"
                                })
                        except ClientError as e:
                            logger.warning("eks_cluster_check_failed", cluster=cluster_name, error=str(e))
                            
        except ClientError as e:
            logger.warning("eks_scan_error", error=str(e))
        
        return zombies


@registry.register("aws")
class IdleElastiCachePlugin(ZombiePlugin):
    """
    Detects ElastiCache clusters with low utilization.
    Uses CloudWatch metrics or CUR data to identify idle caches.
    """
    
    @property
    def category_key(self) -> str:
        return "idle_elasticache_clusters"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] | None = None, 
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        zombies = []
        days = 7
        
        # Check for CUR-based detection first
        cur_records = kwargs.get("cur_records")
        if cur_records:
            from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer
            analyzer = CURUsageAnalyzer(cur_records)
            return analyzer.find_idle_elasticache_clusters(days=days)
        
        # Fallback to CloudWatch
        try:
            async with self._get_client(session, "elasticache", region, credentials, config=config) as elasticache:
                async with self._get_client(session, "cloudwatch", region, credentials, config=config) as cloudwatch:
                    paginator = elasticache.get_paginator("describe_cache_clusters")
                    async for page in paginator.paginate(ShowCacheNodeInfo=True):
                        for cluster in page.get("CacheClusters", []):
                            cluster_id = cluster["CacheClusterId"]
                            node_type = cluster.get("CacheNodeType", "unknown")
                            engine = cluster.get("Engine", "redis")
                            
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days)
                                
                                # Check CPU utilization
                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/ElastiCache",
                                    MetricName="CPUUtilization",
                                    Dimensions=[{"Name": "CacheClusterId", "Value": cluster_id}],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=604800,
                                    Statistics=["Average"]
                                )
                                
                                datapoints = metrics.get("Datapoints", [])
                                avg_cpu = datapoints[0].get("Average", 0) if datapoints else 0
                                
                                if avg_cpu < 5.0:  # Less than 5% CPU
                                    monthly_cost = PricingService.estimate_monthly_waste(
                                        provider="aws",
                                        resource_type="elasticache",
                                        resource_size=node_type,
                                        region=region
                                    )
                                    zombies.append({
                                        "resource_id": cluster_id,
                                        "resource_type": "ElastiCache Cluster",
                                        "node_type": node_type,
                                        "engine": engine,
                                        "avg_cpu": round(avg_cpu, 2),
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "Cache cluster shows minimal activity. Consider deleting.",
                                        "action": "delete_elasticache_cluster",
                                        "confidence_score": 0.90,
                                        "explainability_notes": f"ElastiCache cluster has avg CPU of {avg_cpu:.1f}% over {days} days.",
                                        "detection_method": "cloudwatch-metrics"
                                    })
                            except ClientError as e:
                                logger.warning("elasticache_metric_fetch_failed", cluster=cluster_id, error=str(e))
                                
        except ClientError as e:
            logger.warning("elasticache_scan_error", error=str(e))
        
        return zombies


@registry.register("aws")
class IdleSageMakerNotebooksPlugin(ZombiePlugin):
    """
    Detects SageMaker notebook instances that are running but unused.
    These are common sources of waste ($50-500/month per notebook).
    """
    
    @property
    def category_key(self) -> str:
        return "idle_sagemaker_notebooks"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] | None = None, 
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        zombies = []
        days_idle_threshold = 7
        
        try:
            async with self._get_client(session, "sagemaker", region, credentials, config=config) as sagemaker:
                paginator = sagemaker.get_paginator("list_notebook_instances")
                async for page in paginator.paginate():
                    for notebook in page.get("NotebookInstances", []):
                        name = notebook["NotebookInstanceName"]
                        status = notebook.get("NotebookInstanceStatus", "")
                        instance_type = notebook.get("InstanceType", "unknown")
                        
                        # Only check running notebooks
                        if status != "InService":
                            continue
                        
                        try:
                            # Get last modified time
                            details = await sagemaker.describe_notebook_instance(
                                NotebookInstanceName=name
                            )
                            last_modified = details.get("LastModifiedTime")
                            
                            if last_modified:
                                days_since_modified = (
                                    datetime.now(timezone.utc) - last_modified
                                ).days
                                
                                if days_since_modified > days_idle_threshold:
                                    monthly_cost = PricingService.estimate_monthly_waste(
                                        provider="aws",
                                        resource_type="sagemaker_notebook",
                                        resource_size=instance_type,
                                        region=region
                                    )
                                    zombies.append({
                                        "resource_id": name,
                                        "resource_type": "SageMaker Notebook",
                                        "instance_type": instance_type,
                                        "days_since_modified": days_since_modified,
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": f"Notebook not modified in {days_since_modified} days. Consider stopping.",
                                        "action": "stop_sagemaker_notebook",
                                        "confidence_score": 0.92,
                                        "explainability_notes": f"SageMaker notebook '{name}' has been running but not modified for {days_since_modified} days.",
                                        "detection_method": "api-scan"
                                    })
                        except ClientError as e:
                            logger.warning("sagemaker_notebook_check_failed", notebook=name, error=str(e))
                            
        except ClientError as e:
            logger.warning("sagemaker_notebook_scan_error", error=str(e))
        
        return zombies
