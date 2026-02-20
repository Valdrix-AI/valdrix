"""
Azure Storage Plugins - Zero-Cost Zombie Detection.

Detects unattached disks and old snapshots using Resource Graph (free).
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("azure")
class UnattachedDisksPlugin(ZombiePlugin):
    """Detect unattached Managed Disks."""

    @property
    def category_key(self) -> str:
        return "unattached_azure_disks"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, str] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        """Scan for unattached disks using Compute API (free)."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        zombies = []

        cost_records = kwargs.get("cost_records")
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_unattached_disks()

        try:
            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = ComputeManagementClient(az_creds, subscription_id)

            async for disk in client.disks.list():
                # Unattached disk has disk_state = "Unattached"
                if disk.disk_state == "Unattached":
                    size_gb = disk.disk_size_gb or 0
                    # Estimate cost based on disk type and size
                    # Standard HDD: ~$0.04/GB, Premium SSD: ~$0.12/GB
                    sku_name = getattr(getattr(disk, "sku", None), "name", "")
                    price_per_gb = 0.12 if "premium" in str(sku_name).lower() else 0.04
                    estimated_cost = size_gb * price_per_gb

                    zombies.append(
                        {
                            "resource_id": disk.id,
                            "resource_name": disk.name,
                            "resource_type": "Managed Disk",
                            "location": disk.location,
                            "size_gb": size_gb,
                            "disk_sku": disk.sku.name if disk.sku else "Unknown",
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Snapshot and delete if not needed",
                            "action": "delete_disk",
                            "supports_backup": True,
                            "confidence_score": 0.95,
                            "explainability_notes": f"Disk is unattached. Size: {size_gb} GB, SKU: {disk.sku.name if disk.sku else 'Unknown'}.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_disk_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class OldSnapshotsPlugin(ZombiePlugin):
    """Detect old disk snapshots."""

    @property
    def category_key(self) -> str:
        return "old_azure_snapshots"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, str] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        """Scan for snapshots older than retention period."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        zombies = []
        age_days = kwargs.get("age_days", 90)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=age_days)

        try:
            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = ComputeManagementClient(az_creds, subscription_id)

            async for snapshot in client.snapshots.list():
                creation_time = snapshot.time_created

                if creation_time and creation_time < cutoff_date:
                    size_gb = snapshot.disk_size_gb or 0
                    # Snapshot storage: ~$0.05/GB/month
                    estimated_cost = size_gb * 0.05
                    age = (datetime.now(timezone.utc) - creation_time).days

                    zombies.append(
                        {
                            "resource_id": snapshot.id,
                            "resource_name": snapshot.name,
                            "resource_type": "Disk Snapshot",
                            "location": snapshot.location,
                            "size_gb": size_gb,
                            "age_days": age,
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Delete if no longer needed for recovery",
                            "action": "delete_snapshot",
                            "confidence_score": 0.75,
                            "explainability_notes": f"Snapshot is {age} days old. Review retention policy.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_snapshot_scan_error", error=str(e))

        return zombies
