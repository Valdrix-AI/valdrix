"""
CUR Usage Analyzer

Analyzes AWS Cost and Usage Report (CUR) data to infer resource utilization
without making CloudWatch API calls. This enables zero-API-cost idle detection.

Key Insight: CUR contains `UsageAmount` for each resource. Low UsageAmount
for compute resources (e.g., EC2 BoxUsage) correlates with low utilization.
"""

from typing import List, Dict, Any
from decimal import Decimal
import structlog

logger = structlog.get_logger()


class CURUsageAnalyzer:
    """
    Analyzes CUR Parquet data to identify underutilized resources.
    Supports: EC2, EBS, RDS, Redshift, NAT Gateway, SageMaker, ElastiCache, EKS.
    """
    
    def __init__(self, cur_records: List[Dict[str, Any]]):
        """
        Initialize with CUR records (already parsed from Parquet).
        
        Args:
            cur_records: List of CUR line items with keys like:
                - line_item_resource_id
                - line_item_usage_type
                - line_item_usage_amount
                - line_item_product_code
                - product_instance_type
        """
        self.records = cur_records

    @staticmethod
    def _safe_decimal(value: Any) -> Decimal:
        """Convert values to Decimal safely, defaulting to 0 on invalid input."""
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _safe_int(value: Any) -> int:
        """Convert values to int safely, defaulting to 0 on invalid input."""
        if value is None or value == "":
            return 0
        try:
            return int(float(value))
        except Exception:
            return 0
    
    def find_low_usage_instances(self, days: int = 14) -> List[Dict[str, Any]]:
        """Identifies EC2 instances with low usage based on CUR data."""
        instance_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonEC2" or "BoxUsage" not in usage_type:
                continue
            if not resource_id.startswith("i-"):
                continue
            
            if resource_id not in instance_usage:
                instance_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "instance_type": record.get("product_instance_type") or "unknown",
                    "cost": Decimal("0"),
                }
            
            instance_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            instance_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        expected_hours = days * 24
        low_usage_instances = []
        for resource_id, data in instance_usage.items():
            usage_ratio = float(data["total_usage_hours"]) / expected_hours if expected_hours > 0 else 0
            
            if usage_ratio < 0.30:
                low_usage_instances.append({
                    "resource_id": resource_id,
                    "resource_type": "EC2 Instance",
                    "instance_type": data["instance_type"],
                    "usage_hours": float(data["total_usage_hours"]),
                    "expected_hours": expected_hours,
                    "usage_ratio": round(usage_ratio, 2),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "Instance shows low usage. Consider stopping or terminating.",
                    "action": "stop_instance",
                    "confidence_score": 0.85,
                    "explainability_notes": f"Instance ran for only {data['total_usage_hours']:.1f}h out of {expected_hours}h expected.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_ec2_analysis_complete", analyzed=len(instance_usage), idle=len(low_usage_instances))
        return low_usage_instances
    
    def find_unused_ebs_volumes(self) -> List[Dict[str, Any]]:
        """Identifies EBS volumes with zero I/O operations."""
        volume_io: Dict[str, Decimal] = {}
        volume_cost: Dict[str, Decimal] = {}
        volume_size: Dict[str, int] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonEC2":
                continue
            
            if "EBS:VolumeUsage" in usage_type and resource_id.startswith("vol-"):
                volume_cost[resource_id] = volume_cost.get(resource_id, Decimal("0")) + self._safe_decimal(
                    record.get("line_item_unblended_cost")
                )
                volume_size[resource_id] = self._safe_int(record.get("line_item_usage_amount"))
            
            if "EBS:VolumeIOUsage" in usage_type and resource_id.startswith("vol-"):
                volume_io[resource_id] = volume_io.get(resource_id, Decimal("0")) + self._safe_decimal(
                    record.get("line_item_usage_amount")
                )
        
        unused_volumes = []
        for vol_id, cost in volume_cost.items():
            io_ops = volume_io.get(vol_id, Decimal("0"))
            if io_ops == 0 and cost > 0:
                unused_volumes.append({
                    "resource_id": vol_id,
                    "resource_type": "EBS Volume",
                    "size_gb": volume_size.get(vol_id, 0),
                    "monthly_cost": float(cost),
                    "io_operations": 0,
                    "recommendation": "Volume has no I/O activity. Likely unattached.",
                    "action": "delete_volume",
                    "confidence_score": 0.90,
                    "detection_method": "cur-usage-analysis"
                })
        
        return unused_volumes

    def find_idle_rds_databases(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Identifies RDS databases with low usage based on CUR data.
        Low InstanceUsage hours indicate the database is rarely accessed.
        """
        rds_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonRDS":
                continue
            if "InstanceUsage" not in usage_type and "Multi-AZUsage" not in usage_type:
                continue
            
            if resource_id not in rds_usage:
                rds_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "db_class": record.get("product_instance_type") or "unknown",
                    "engine": record.get("product_database_engine") or "unknown",
                    "cost": Decimal("0"),
                }
            
            rds_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            rds_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        expected_hours = days * 24
        idle_databases = []
        for resource_id, data in rds_usage.items():
            usage_ratio = float(data["total_usage_hours"]) / expected_hours if expected_hours > 0 else 0
            
            # RDS with low provisioned hours relative to expectation
            if usage_ratio < 0.50:  # Less than 50% uptime for DB is suspicious
                idle_databases.append({
                    "resource_id": resource_id,
                    "resource_type": "RDS Database",
                    "db_class": data["db_class"],
                    "engine": data["engine"],
                    "usage_hours": float(data["total_usage_hours"]),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "Database shows low activity. Consider stopping or deleting.",
                    "action": "stop_rds_instance",
                    "supports_backup": True,
                    "confidence_score": 0.80,
                    "explainability_notes": f"RDS ran for {data['total_usage_hours']:.1f}h out of {expected_hours}h.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_rds_analysis_complete", analyzed=len(rds_usage), idle=len(idle_databases))
        return idle_databases

    def find_idle_redshift_clusters(self, days: int = 7) -> List[Dict[str, Any]]:
        """Identifies Redshift clusters with low usage based on CUR data."""
        redshift_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonRedshift":
                continue
            if "Node" not in usage_type:
                continue
            
            if resource_id not in redshift_usage:
                redshift_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "node_type": record.get("product_instance_type") or "unknown",
                    "cost": Decimal("0"),
                }
            
            redshift_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            redshift_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        expected_hours = days * 24
        idle_clusters = []
        for resource_id, data in redshift_usage.items():
            usage_ratio = float(data["total_usage_hours"]) / expected_hours if expected_hours > 0 else 0
            
            if usage_ratio < 0.30:
                idle_clusters.append({
                    "resource_id": resource_id,
                    "resource_type": "Redshift Cluster",
                    "node_type": data["node_type"],
                    "usage_hours": float(data["total_usage_hours"]),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "Cluster shows minimal usage. Consider pausing or deleting.",
                    "action": "delete_redshift_cluster",
                    "confidence_score": 0.85,
                    "explainability_notes": f"Redshift ran for {data['total_usage_hours']:.1f}h out of {expected_hours}h.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_redshift_analysis_complete", analyzed=len(redshift_usage), idle=len(idle_clusters))
        return idle_clusters

    def find_idle_nat_gateways(self, days: int = 7) -> List[Dict[str, Any]]:
        """Identifies NAT Gateways with low data processing based on CUR data."""
        nat_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonEC2":
                continue
            if "NatGateway" not in usage_type:
                continue
            
            if resource_id not in nat_usage:
                nat_usage[resource_id] = {
                    "resource_id": resource_id,
                    "data_processed_gb": Decimal("0"),
                    "hourly_cost": Decimal("0"),
                    "data_cost": Decimal("0"),
                }
            
            if "NatGateway-Hours" in usage_type:
                nat_usage[resource_id]["hourly_cost"] += self._safe_decimal(
                    record.get("line_item_unblended_cost")
                )
            elif "NatGateway-Bytes" in usage_type:
                nat_usage[resource_id]["data_processed_gb"] += self._safe_decimal(
                    record.get("line_item_usage_amount")
                )
                nat_usage[resource_id]["data_cost"] += self._safe_decimal(
                    record.get("line_item_unblended_cost")
                )
        
        idle_nats = []
        for resource_id, data in nat_usage.items():
            total_cost = float(data["hourly_cost"] + data["data_cost"])
            data_gb = float(data["data_processed_gb"])
            
            # NAT with < 1GB processed in a week is likely underused
            if data_gb < 1.0 and total_cost > 0:
                idle_nats.append({
                    "resource_id": resource_id,
                    "resource_type": "NAT Gateway",
                    "data_processed_gb": round(data_gb, 2),
                    "monthly_cost": round(total_cost, 2),
                    "recommendation": "NAT Gateway has minimal traffic. Consider consolidating.",
                    "action": "manual_review",
                    "confidence_score": 0.80,
                    "explainability_notes": f"NAT processed only {data_gb:.2f} GB in {days} days.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_nat_analysis_complete", analyzed=len(nat_usage), idle=len(idle_nats))
        return idle_nats

    def find_idle_sagemaker_endpoints(self, days: int = 7) -> List[Dict[str, Any]]:
        """Identifies SageMaker endpoints with low usage based on CUR data."""
        sagemaker_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonSageMaker":
                continue
            if "Hosting" not in usage_type and "Endpoint" not in usage_type:
                continue
            
            if resource_id not in sagemaker_usage:
                sagemaker_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "instance_type": record.get("product_instance_type") or "unknown",
                    "cost": Decimal("0"),
                }
            
            sagemaker_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            sagemaker_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        expected_hours = days * 24
        idle_endpoints = []
        for resource_id, data in sagemaker_usage.items():
            usage_ratio = float(data["total_usage_hours"]) / expected_hours if expected_hours > 0 else 0
            
            # SageMaker endpoints with < 20% expected hours likely have no invocations
            if usage_ratio < 0.20:
                idle_endpoints.append({
                    "resource_id": resource_id,
                    "resource_type": "SageMaker Endpoint",
                    "instance_type": data["instance_type"],
                    "usage_hours": float(data["total_usage_hours"]),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "Endpoint shows minimal usage. Consider deleting.",
                    "action": "delete_sagemaker_endpoint",
                    "confidence_score": 0.85,
                    "explainability_notes": f"Endpoint ran for {data['total_usage_hours']:.1f}h out of {expected_hours}h.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_sagemaker_analysis_complete", analyzed=len(sagemaker_usage), idle=len(idle_endpoints))
        return idle_endpoints

    def find_idle_elasticache_clusters(self, days: int = 7) -> List[Dict[str, Any]]:
        """Identifies ElastiCache clusters with low usage based on CUR data."""
        cache_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            usage_type = record.get("line_item_usage_type", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonElastiCache":
                continue
            if "NodeUsage" not in usage_type:
                continue
            
            if resource_id not in cache_usage:
                cache_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "node_type": record.get("product_instance_type") or "unknown",
                    "engine": record.get("product_cache_engine") or "redis",
                    "cost": Decimal("0"),
                }
            
            cache_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            cache_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        expected_hours = days * 24
        idle_clusters = []
        for resource_id, data in cache_usage.items():
            usage_ratio = float(data["total_usage_hours"]) / expected_hours if expected_hours > 0 else 0
            
            if usage_ratio < 0.30:
                idle_clusters.append({
                    "resource_id": resource_id,
                    "resource_type": "ElastiCache Cluster",
                    "node_type": data["node_type"],
                    "engine": data["engine"],
                    "usage_hours": float(data["total_usage_hours"]),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "Cache cluster shows low activity. Review usage patterns.",
                    "action": "delete_elasticache_cluster",
                    "confidence_score": 0.80,
                    "explainability_notes": f"ElastiCache ran for {data['total_usage_hours']:.1f}h out of {expected_hours}h.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_elasticache_analysis_complete", analyzed=len(cache_usage), idle=len(idle_clusters))
        return idle_clusters

    def find_idle_eks_clusters(self, days: int = 7) -> List[Dict[str, Any]]:
        """Identifies EKS clusters based on CUR control plane charges."""
        eks_usage: Dict[str, Dict[str, Any]] = {}
        
        for record in self.records:
            resource_id = record.get("line_item_resource_id", "")
            product_code = record.get("line_item_product_code", "")
            
            if product_code != "AmazonEKS":
                continue
            
            if resource_id not in eks_usage:
                eks_usage[resource_id] = {
                    "resource_id": resource_id,
                    "total_usage_hours": Decimal("0"),
                    "cost": Decimal("0"),
                }
            
            eks_usage[resource_id]["total_usage_hours"] += self._safe_decimal(
                record.get("line_item_usage_amount")
            )
            eks_usage[resource_id]["cost"] += self._safe_decimal(
                record.get("line_item_unblended_cost")
            )
        
        # EKS clusters are charged $0.10/hour for control plane
        # If running full time but with minimal node costs, it may be idle
        idle_clusters = []
        for resource_id, data in eks_usage.items():
            if float(data["cost"]) > 50:  # Charged for control plane
                idle_clusters.append({
                    "resource_id": resource_id,
                    "resource_type": "EKS Cluster",
                    "usage_hours": float(data["total_usage_hours"]),
                    "monthly_cost": float(data["cost"]),
                    "recommendation": "EKS cluster detected. Verify workload activity.",
                    "action": "manual_review",
                    "confidence_score": 0.70,  # Lower confidence - needs pod-level analysis
                    "explainability_notes": f"EKS control plane cost: ${data['cost']:.2f}. Review node utilization.",
                    "detection_method": "cur-usage-analysis"
                })
        
        logger.info("cur_eks_analysis_complete", analyzed=len(eks_usage), flagged=len(idle_clusters))
        return idle_clusters
