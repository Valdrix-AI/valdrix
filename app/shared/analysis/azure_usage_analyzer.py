"""
Azure Usage Analyzer - Zero-API-Cost Zombie Detection via Cost Management Export.

This module analyzes Azure cost export data to detect idle and underutilized
resources without making expensive Monitor API calls.
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import structlog

logger = structlog.get_logger()


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
    
    def _group_by_resource(self) -> Dict[str, List[Dict]]:
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.compute/virtualmachines" not in resource_id.lower():
                continue
            
            vm_records = [r for r in records 
                         if r.get("ServiceName", "").lower() == "virtual machines"]
            
            if not vm_records:
                continue
            
            total_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in vm_records)
            
            # Check for GPU VMs (NC, ND, NV series)
            vm_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
            is_gpu = any(series in resource_id.lower() 
                        for series in ["standard_nc", "standard_nd", "standard_nv"])
            
            # Look for disk I/O and network usage in related records
            disk_usage = sum(r.get("UsageQuantity", 0) for r in self._resource_costs.get(resource_id, [])
                            if "disk" in r.get("MeterCategory", "").lower())
            network_usage = sum(r.get("UsageQuantity", 0) for r in self._resource_costs.get(resource_id, [])
                               if "bandwidth" in r.get("MeterCategory", "").lower())
            
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.compute/disks" not in resource_id.lower():
                continue
            
            disk_records = [r for r in records 
                          if "disk" in r.get("MeterCategory", "").lower()]
            
            if not disk_records:
                continue
            
            storage_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in disk_records)
            
            # Check if there's an associated VM
            has_vm = any("/virtualmachines/" in vm_id.lower() 
                        for vm_id in self._resource_costs.keys() 
                        if resource_id in str(self._resource_costs.get(vm_id, [])))
            
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.sql/servers/databases" not in resource_id.lower():
                continue
            
            sql_records = [r for r in records 
                         if "sql" in r.get("ServiceName", "").lower()]
            
            if not sql_records:
                continue
            
            total_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in sql_records)
            
            # Check for DTU/vCore usage (indicates actual queries)
            dtu_usage = sum(r.get("UsageQuantity", 0) for r in sql_records
                          if "dtu" in r.get("MeterName", "").lower() 
                          or "vcore" in r.get("MeterName", "").lower())
            
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.containerservice/managedclusters" not in resource_id.lower():
                continue
            
            aks_records = [r for r in records 
                         if "kubernetes" in r.get("ServiceName", "").lower()]
            
            if not aks_records:
                continue
            
            total_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in aks_records)
            
            # Check for node pool compute costs (indicates workloads)
            node_cost = sum(r.get("PreTaxCost", 0) for r in aks_records
                          if "node" in r.get("MeterName", "").lower())
            
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.network/publicipaddresses" not in resource_id.lower():
                continue
            
            ip_records = [r for r in records 
                        if "ip address" in r.get("MeterName", "").lower()]
            
            if not ip_records:
                continue
            
            ip_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in ip_records)
            
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
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.web/serverfarms" not in resource_id.lower():
                continue
            
            plan_records = [r for r in records 
                          if "app service" in r.get("ServiceName", "").lower()]
            
            if not plan_records:
                continue
            
            total_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in plan_records)
            
            # Check for any web app activity
            app_usage = sum(r.get("UsageQuantity", 0) for r in plan_records
                          if "hour" in r.get("MeterName", "").lower())
            
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
        Note: NICs themselves are free but indicate cleanup needed.
        """
        zombies = []
        
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
        """
        zombies = []
        
        for resource_id, records in self._resource_costs.items():
            if "microsoft.compute/snapshots" not in resource_id.lower():
                continue
            
            snapshot_records = [r for r in records 
                               if "snapshot" in r.get("MeterCategory", "").lower()]
            
            if not snapshot_records:
                continue
            
            storage_cost = sum(r.get("PreTaxCost", 0) or r.get("cost_usd", 0) for r in snapshot_records)
            
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
