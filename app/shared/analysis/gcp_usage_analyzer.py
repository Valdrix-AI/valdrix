"""
GCP Usage Analyzer - Zero-API-Cost Zombie Detection via BigQuery Billing Export.

This module analyzes GCP billing export data from BigQuery to detect idle and
underutilized resources without making expensive monitoring API calls.
"""
from typing import Any, Dict, List
from datetime import datetime, timezone
from collections import defaultdict
import structlog

logger = structlog.get_logger()


class GCPUsageAnalyzer:
    """
    Analyzes GCP BigQuery billing export data to detect zombie resources.
    
    Zero-Cost Architecture:
    - Uses BigQuery billing export (free tier: 1TB query/month)
    - No Cloud Monitoring API calls (which cost money)
    - Detection based on usage patterns in billing data
    """
    
    def __init__(self, billing_records: list[dict[str, Any]]):
        """
        Initialize with billing records from BigQuery export.
        
        Args:
            billing_records: List of dicts with keys like:
                - resource_id, service, sku_description, usage_amount,
                - usage_unit, cost, currency, usage_start_time, labels
        """
        self.records = billing_records
        self._resource_costs = self._group_by_resource()
    
    def _group_by_resource(self) -> dict[str, list[dict[str, Any]]]:
        """Group billing records by resource_id for analysis."""
        grouped = defaultdict(list)
        for record in self.records:
            resource_id = record.get("resource_id") or record.get("resource.name", "")
            if resource_id:
                grouped[resource_id].append(record)
        return grouped
    
    def find_idle_vms(self, days: int = 7, cpu_threshold: float = 5.0) -> List[Dict[str, Any]]:
        """
        Detect idle Compute Engine VMs based on billing data patterns.
        
        An idle VM is identified by:
        - Running for `days` with cost but minimal CPU usage hours
        - No network egress indicating traffic
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            # Filter for Compute Engine instances
            compute_records = [r for r in records 
                             if r.get("service", "").lower() == "compute engine"
                             and ("/instances/" in resource_id or "/machine-types/" in resource_id)]
            
            if not compute_records:
                continue
            
            total_cost = sum(float(r.get("cost", 0) or 0) for r in compute_records)
            total_cpu_hours = sum(float(r.get("usage_amount", 0) or 0) for r in compute_records
                                 if any(x in r.get("sku_description", "").lower() for x in ["cpu", "core", "vcpus"]))
            total_network = sum(float(r.get("usage_amount", 0) or 0) for r in compute_records
                               if "egress" in r.get("sku_description", "").lower())
            
            # Heuristic: Low CPU hours relative to running time indicates idle
            instance_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
            
            # Check for GPU instances - higher priority
            is_gpu = any("gpu" in r.get("sku_description", "").lower() for r in compute_records)
            
            if total_cpu_hours < cpu_threshold and total_cost > 0:
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": instance_name,
                    "resource_type": "Compute Engine VM" + (" (GPU)" if is_gpu else ""),
                    "monthly_cost": round(total_cost * (30 / days), 2),
                    "cpu_hours": round(total_cpu_hours, 2),
                    "network_egress_gb": round(total_network, 2),
                    "recommendation": "Stop or delete idle VM",
                    "action": "stop_vm",
                    "confidence_score": 0.90 if total_cpu_hours < 1 else 0.75,
                    "explainability_notes": f"VM has only {total_cpu_hours:.1f} CPU hours over {days} days with minimal network activity."
                })
        
        return zombies
    
    def find_unattached_disks(self) -> List[Dict[str, Any]]:
        """
        Detect unattached Persistent Disks from billing data.
        
        Disks with storage cost but no read/write operations are likely orphaned.
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            disk_records = [r for r in records 
                          if "persistent disk" in r.get("service", "").lower()
                          or "storage pd" in r.get("sku_description", "").lower()]
            
            if not disk_records:
                continue
            
            storage_cost = sum(float(r.get("cost", 0) or 0) for r in disk_records
                              if "capacity" in r.get("sku_description", "").lower())
            io_operations = sum(float(r.get("usage_amount", 0) or 0) for r in disk_records
                               if "read" in r.get("sku_description", "").lower() 
                               or "write" in r.get("sku_description", "").lower())
            
            if storage_cost > 0 and io_operations == 0:
                disk_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": disk_name,
                    "resource_type": "Persistent Disk",
                    "monthly_cost": round(storage_cost * 30, 2),
                    "recommendation": "Snapshot and delete if not needed",
                    "action": "delete_disk",
                    "confidence_score": 0.95,
                    "explainability_notes": "Disk has storage costs but zero I/O operations, indicating it's likely orphaned."
                })
        
        return zombies
    
    def find_idle_cloud_sql(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Detect idle Cloud SQL instances from billing data.
        
        Idle databases have instance costs but minimal connection/query activity.
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            sql_records = [r for r in records 
                         if "cloud sql" in r.get("service", "").lower()]
            
            if not sql_records:
                continue
            
            instance_cost = sum(float(r.get("cost", 0) or 0) for r in sql_records)
            network_bytes = sum(float(r.get("usage_amount", 0) or 0) for r in sql_records
                               if "network" in r.get("sku_description", "").lower())
            # Calculate storage usage for context
            total_storage_gb = sum(float(r.get("usage_amount", 0) or 0) for r in sql_records
                               if "storage" in r.get("sku_description", "").lower())
            
            # Low network activity indicates no connections
            if instance_cost > 0 and network_bytes < 1:  # Less than 1 GB
                instance_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": instance_name,
                    "resource_type": "Cloud SQL",
                    "monthly_cost": round(instance_cost * (30 / days), 2),
                    "recommendation": "Stop instance or delete if not needed",
                    "action": "stop_cloud_sql",
                    "confidence_score": 0.88,
                    "explainability_notes": f"Cloud SQL instance has minimal network traffic ({network_bytes:.2f} GB), {total_storage_gb:.1f} GB storage, indicating no active connections."
                })
        
        return zombies
    
    def find_empty_gke_clusters(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Detect GKE clusters with no workloads (only control plane cost).
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            gke_records = [r for r in records 
                         if "kubernetes engine" in r.get("service", "").lower()]
            
            if not gke_records:
                continue
            
            control_plane_cost = sum(float(r.get("cost", 0) or 0) for r in gke_records
                                    if "cluster management" in r.get("sku_description", "").lower())
            node_cost = sum(float(r.get("cost", 0) or 0) for r in gke_records
                          if "node" in r.get("sku_description", "").lower())
            
            # Cluster with control plane cost but no node costs
            if control_plane_cost > 0 and node_cost == 0:
                cluster_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": cluster_name,
                    "resource_type": "GKE Cluster",
                    "monthly_cost": round(control_plane_cost * (30 / days), 2),
                    "recommendation": "Delete empty cluster",
                    "action": "delete_gke_cluster",
                    "confidence_score": 0.92,
                    "explainability_notes": "GKE cluster has control plane costs but no node costs, indicating no workloads."
                })
        
        return zombies
    
    def find_idle_cloud_functions(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Detect Cloud Functions with zero invocations.
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            function_records = [r for r in records 
                               if "cloud functions" in r.get("service", "").lower()]
            
            if not function_records:
                continue
            
            invocation_count = sum(float(r.get("usage_amount", 0) or 0) for r in function_records
                                  if "invocation" in r.get("sku_description", "").lower())
            
            if invocation_count == 0:
                function_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": function_name,
                    "resource_type": "Cloud Function",
                    "monthly_cost": 0.0,  # Functions cost per invocation
                    "invocations": 0,
                    "recommendation": "Delete unused function",
                    "action": "delete_cloud_function",
                    "confidence_score": 0.85,
                    "explainability_notes": f"Cloud Function has zero invocations over {days} days."
                })
        
        return zombies
    
    def find_idle_cloud_run(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Detect Cloud Run services with zero requests.
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            run_records = [r for r in records 
                         if "cloud run" in r.get("service", "").lower()]
            
            if not run_records:
                continue
            
            request_count = sum(float(r.get("usage_amount", 0) or 0) for r in run_records
                               if "request" in r.get("sku_description", "").lower())
            cpu_time = sum(float(r.get("usage_amount", 0) or 0) for r in run_records
                          if "cpu" in r.get("sku_description", "").lower())
            
            if request_count == 0 and cpu_time == 0:
                service_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": service_name,
                    "resource_type": "Cloud Run Service",
                    "monthly_cost": 0.0,
                    "recommendation": "Delete unused service",
                    "action": "delete_cloud_run",
                    "confidence_score": 0.85,
                    "explainability_notes": f"Cloud Run service has zero requests over {days} days."
                })
        
        return zombies
    
    def find_orphan_ips(self) -> List[Dict[str, Any]]:
        """
        Detect external IPs with charges but no associated compute resource.
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            ip_records = [r for r in records 
                         if "external ip" in r.get("sku_description", "").lower()
                         or "static ip" in r.get("sku_description", "").lower()]
            
            if not ip_records:
                continue
            
            ip_cost = sum(float(r.get("cost", 0) or 0) for r in ip_records)
            
            # External IPs only cost money when NOT attached to a running VM
            if ip_cost > 0:
                ip_address = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": ip_address,
                    "resource_type": "External IP Address",
                    "monthly_cost": round(ip_cost * 30, 2),
                    "recommendation": "Release if not needed",
                    "action": "release_ip",
                    "confidence_score": 0.90,
                    "explainability_notes": "Static external IP is incurring charges, likely not attached to a running resource."
                })
        
        return zombies
    
    def find_old_snapshots(self, age_days: int = 90) -> List[Dict[str, Any]]:
        """
        Detect old disk snapshots with ongoing storage costs.
        """
        zombies = []
        now = datetime.now(timezone.utc)
        
        for resource_id, records in self._resource_costs.items():
            snapshot_records = [r for r in records 
                               if "snapshot" in r.get("sku_description", "").lower()]
            
            if not snapshot_records:
                continue
            
            storage_cost = sum(float(r.get("cost", 0) or 0) for r in snapshot_records)
            
            # GCP-DET-1: Use age_days parameter for snapshot detection
            oldest_record = min(snapshot_records, key=lambda x: x.get("usage_start_time", now))
            record_start = oldest_record.get("usage_start_time")
            
            is_old = False
            if record_start:
                age = (now - record_start).days
                is_old = age >= age_days
            
            if storage_cost > 0 and is_old:
                snapshot_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": snapshot_name,
                    "resource_type": "Disk Snapshot",
                    "monthly_cost": round(storage_cost * 30, 2),
                    "recommendation": "Review and delete if no longer needed",
                    "action": "delete_snapshot",
                    "confidence_score": 0.70,
                    "explainability_notes": f"Snapshot (first seen: {record_start}) has ongoing storage costs. Review retention policy."
                })
        
        return zombies
