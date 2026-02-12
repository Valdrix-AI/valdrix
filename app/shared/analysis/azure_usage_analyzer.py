"""
Azure Usage Analyzer - Zero-API-Cost Zombie Detection via Cost Management Export.

This module analyzes Azure cost export data to detect idle and underutilized
resources without making expensive Monitor API calls.
"""
from typing import List, Dict, Any
from collections import defaultdict
import structlog

logger = structlog.get_logger()


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class AzureUsageAnalyzer:
    """
    Analyzes Azure Cost Management export data to detect zombie resources.
    
    Zero-Cost Architecture:
    - Uses Cost Management exports to Blob Storage (free)
    - No Monitor API calls (which cost money)
    - Detection based on usage patterns in cost data
    """
    
    def __init__(self, cost_records: List[Dict[str, Any]]):
        """
        Initialize with cost records from Cost Management export.
        
        Args:
            cost_records: List of dicts with keys like:
                - ResourceId, ResourceName, ResourceType, ServiceName,
                - PreTaxCost, UsageQuantity, UsageDate, Tags
        """
        self.records = cost_records
        self._resource_costs = self._group_by_resource()
    
    def _group_by_resource(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group cost records by ResourceId for analysis."""
        grouped = defaultdict(list)
        for record in self.records:
            resource_id = record.get("ResourceId") or record.get("resource_id", "")
            if resource_id:
                grouped[resource_id.lower()].append(record)
        return grouped
    
    def find_idle_vms(self, days: int = 7, cost_threshold: float = 50.0) -> List[Dict[str, Any]]:
        """
        Detect idle Azure VMs based on cost export data patterns.
        
        An idle VM is identified by:
        - Running with compute cost but minimal disk/network usage
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.compute/virtualmachines" not in resource_key.lower():
                continue
            
            vm_records = [r for r in records 
                         if r.get("ServiceName", "").lower() == "virtual machines"]
            
            if not vm_records:
                continue
            
            total_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in vm_records)
            
            # Get original resource ID from records (not the lowercase key)
            resource_id = vm_records[0].get("ResourceId") or vm_records[0].get("resource_id", resource_key)
            
            # Check for GPU VMs (NC, ND, NV series)
            vm_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
            is_gpu = any(series in resource_id.lower() 
                        for series in ["standard_nc", "standard_nd", "standard_nv", "_nc", "_nd", "_nv", "gpu"])
            
            # Look for disk I/O and network usage in related records
            # Broaden search to MeterName and MeterCategory
            disk_usage = sum(safe_float(r.get("UsageQuantity", 0)) for r in self._resource_costs.get(resource_key, [])
                            if any(term in str(r.get("MeterCategory", "")).lower() or 
                                  term in str(r.get("MeterName", "")).lower() 
                                  for term in ["disk", "storage"]))
            
            network_usage = sum(safe_float(r.get("UsageQuantity", 0)) for r in self._resource_costs.get(resource_key, [])
                               if any(term in str(r.get("MeterCategory", "")).lower() or 
                                     term in str(r.get("MeterName", "")).lower() 
                                     for term in ["bandwidth", "network", "throughput"]))
            
            # Low disk/network activity with significant compute cost indicates idle
            if total_cost > cost_threshold and disk_usage < 1 and network_usage < 1:
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": vm_name,
                    "resource_type": "Virtual Machine" + (" (GPU)" if is_gpu else ""),
                    "monthly_cost": round(total_cost * (30 / days), 2),
                    "recommendation": "Stop or deallocate if not needed",
                    "action": "deallocate_vm",
                    "confidence_score": 0.85 if is_gpu else 0.75,
                    "explainability_notes": f"VM has ${total_cost:.2f} in compute costs over {days} days but minimal disk/network activity."
                })
        
        return zombies
    
    def find_unattached_disks(self) -> List[Dict[str, Any]]:
        """
        Detect unattached Managed Disks from cost data.
        
        Disks with storage cost but no associated VM usage.
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.compute/disks" not in resource_key:
                continue
            
            disk_records = [r for r in records 
                          if any(term in str(r.get("MeterCategory", "")).lower() or 
                                term in str(r.get("ServiceName", "")).lower() 
                                for term in ["disk", "storage"])]
            
            if not disk_records:
                continue
            
            storage_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in disk_records)
            
            # Use original ResourceId for results
            resource_id = disk_records[0].get("ResourceId") or disk_records[0].get("resource_id", resource_key)
            
            # Check for disk ID in VM's related resource records
            has_vm = False
            for vm_id in self._resource_costs.keys():
                if "/virtualmachines/" in vm_id:
                    vm_records = self._resource_costs.get(vm_id, [])
                    if any(resource_id.lower() == str(val).lower() for r in vm_records for val in r.values()):
                        has_vm = True
                        break
            
            if storage_cost > 0 and not has_vm:
                disk_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": disk_name,
                    "resource_type": "Managed Disk",
                    "monthly_cost": round(storage_cost * 30, 2),
                    "recommendation": "Snapshot and delete if not needed",
                    "action": "delete_disk",
                    "supports_backup": True,
                    "confidence_score": 0.90,
                    "explainability_notes": "Managed Disk has storage costs but appears unattached."
                })
        
        return zombies
    
    def find_idle_sql_databases(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Detect idle Azure SQL databases from cost data.
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.sql/servers" not in resource_key or "/databases/" not in resource_key:
                continue
            
            sql_records = [r for r in records 
                         if any(term in str(r.get("ServiceName", "")).lower() for term in ["sql", "database"])]
            
            if not sql_records:
                continue
            
            total_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in sql_records)
            
            # Use original ResourceId for results
            resource_id = sql_records[0].get("ResourceId") or sql_records[0].get("resource_id", resource_key)
            
            # Check for DTU/vCore usage (indicates actual queries)
            dtu_usage = sum(safe_float(r.get("UsageQuantity", 0)) for r in sql_records
                          if any(term in str(r.get("MeterName", "")).lower() for term in ["dtu", "vcore"]))
            
            if total_cost > 0 and dtu_usage < 1:
                db_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": db_name,
                    "resource_type": "Azure SQL Database",
                    "monthly_cost": round(total_cost * (30 / days), 2),
                    "recommendation": "Pause or delete if not needed",
                    "action": "pause_sql",
                    "confidence_score": 0.85,
                    "explainability_notes": f"SQL Database has minimal DTU/vCore usage over {days} days."
                })
        
        return zombies
    
    def find_idle_aks_clusters(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Detect AKS clusters with minimal workload usage.
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.containerservice/managedclusters" not in resource_key:
                continue
            
            aks_records = [r for r in records 
                         if any(term in str(r.get("ServiceName", "")).lower() for term in ["kubernetes", "aks"])]
            
            if not aks_records:
                continue
            
            total_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in aks_records)
            
            # Use original ResourceId for results
            resource_id = aks_records[0].get("ResourceId") or aks_records[0].get("resource_id", resource_key)
            
            # Check for node pool compute costs (indicates workloads)
            node_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in aks_records
                          if any(term in str(r.get("MeterName", "")).lower() for term in ["node", "agent pool"]))
            
            if total_cost > 0 and node_cost == 0:
                cluster_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": cluster_name,
                    "resource_type": "AKS Cluster",
                    "monthly_cost": round(total_cost * (30 / days), 2),
                    "recommendation": "Delete if no workloads",
                    "action": "delete_aks",
                    "confidence_score": 0.88,
                    "explainability_notes": "AKS cluster has control plane cost but no node pool compute costs."
                })
        
        return zombies
    
    def find_orphan_public_ips(self) -> List[Dict[str, Any]]:
        """
        Detect unused Public IP addresses.
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.network/publicipaddresses" not in resource_key:
                continue
            
            ip_records = [r for r in records 
                        if any(term in str(r.get("MeterName", "")).lower() or 
                              term in str(r.get("ServiceName", "")).lower() 
                              for term in ["ip address", "public ip"])]
            
            if not ip_records:
                continue
            
            ip_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in ip_records)
            
            # Use original ResourceId for results
            resource_id = ip_records[0].get("ResourceId") or ip_records[0].get("resource_id", resource_key)
            
            # Public IPs cost when static and not associated
            if ip_cost > 0:
                ip_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": ip_name,
                    "resource_type": "Public IP Address",
                    "monthly_cost": round(ip_cost * 30, 2),
                    "recommendation": "Delete if not needed",
                    "action": "delete_ip",
                    "confidence_score": 0.90,
                    "explainability_notes": "Static Public IP incurring charges, likely not associated."
                })
        
        return zombies
    
    def find_unused_app_service_plans(self) -> List[Dict[str, Any]]:
        """
        Detect App Service Plans with no apps.
        """
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.web/serverfarms" not in resource_key:
                continue
            
            plan_records = [r for r in records 
                          if any(term in str(r.get("ServiceName", "")).lower() for term in ["app service", "server farm"])]
            
            if not plan_records:
                continue
            
            total_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in plan_records)
            
            # Use original ResourceId for results
            resource_id = plan_records[0].get("ResourceId") or plan_records[0].get("resource_id", resource_key)
            
            # Check for any web app activity
            app_usage = sum(safe_float(r.get("UsageQuantity", 0)) for r in plan_records
                          if "hour" in str(r.get("MeterName", "")).lower())
            
            if total_cost > 0 and app_usage == 0:
                plan_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": plan_name,
                    "resource_type": "App Service Plan",
                    "monthly_cost": round(total_cost * 30, 2),
                    "recommendation": "Delete if no apps deployed",
                    "action": "delete_app_service_plan",
                    "confidence_score": 0.85,
                    "explainability_notes": "App Service Plan has cost but no app compute usage."
                })
        
        return zombies
    
    def find_orphan_nics(self) -> List[Dict[str, Any]]:
        """
        Detect Network Interfaces not attached to any VM.
        
        NOTE: This analyzer does not implement NIC orphan detection from cost data 
        and returns an empty list. NICs are free and typically do not appear as 
        line items in costExports. Orphan NICs should be identified via Azure 
        Resource Graph or Network APIs.
        """
        zombies: List[Dict[str, Any]] = []
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.network/networkinterfaces" not in resource_id.lower():
                continue
            
            # NICs are free, but if they exist in cost data, they're associated with something
            # We flag orphan NICs from Resource Graph, not cost data
            pass
        
        return zombies
    
    def find_old_snapshots(self, age_days: int = 90) -> List[Dict[str, Any]]:
        """
        Detect old disk snapshots with ongoing storage costs.
        
        Args:
            age_days: Minimum age of snapshot to flag (reserved for future filtering)
        """
        _ = age_days # Satisfy lint
        zombies = []
        
        for resource_key, records in self._resource_costs.items():
            if "microsoft.compute/snapshots" not in resource_key:
                continue
            
            snapshot_records = [r for r in records 
                               if any(term in str(r.get("MeterCategory", "")).lower() or 
                                     term in str(r.get("ServiceName", "")).lower() 
                                     for term in ["snapshot", "storage"])]
            
            if not snapshot_records:
                continue
            
            storage_cost = sum(safe_float(r.get("PreTaxCost", 0)) for r in snapshot_records)
            
            # Use original ResourceId for results
            resource_id = snapshot_records[0].get("ResourceId") or snapshot_records[0].get("resource_id", resource_key)
            
            if storage_cost > 0:
                snapshot_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                zombies.append({
                    "resource_id": resource_id,
                    "resource_name": snapshot_name,
                    "resource_type": "Disk Snapshot",
                    "monthly_cost": round(storage_cost * 30, 2),
                    "recommendation": "Review and delete if no longer needed",
                    "action": "delete_snapshot",
                    "confidence_score": 0.70,
                    "explainability_notes": "Snapshot has ongoing storage costs. Review retention policy."
                })
        
        return zombies
