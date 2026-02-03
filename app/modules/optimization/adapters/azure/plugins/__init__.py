"""
Azure Zombie Detection Plugins.

All plugins use Cost Management export data for zero-cost detection.
"""
# New zero-cost plugins (cost export first)
from .compute import IdleVmsPlugin, IdleGpuVmsPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanPublicIpsPlugin, OrphanNicsPlugin, OrphanNsgsPlugin
from .database import IdleSqlDatabasesPlugin
from .containers import IdleAksClusterPlugin, UnusedAppServicePlansPlugin

# Legacy plugins (for backward compatibility)
from .idle_vms import AzureIdleVMPlugin
from .unattached_disks import AzureUnattachedDisksPlugin
from .orphaned_images import AzureOrphanedImagesPlugin
from .orphaned_ips import AzureOrphanedIpsPlugin

__all__ = [
    # New Zero-Cost Plugins
    "IdleVmsPlugin",
    "IdleGpuVmsPlugin",
    "UnattachedDisksPlugin",
    "OldSnapshotsPlugin",
    "OrphanPublicIpsPlugin",
    "OrphanNicsPlugin",
    "OrphanNsgsPlugin",
    "IdleSqlDatabasesPlugin",
    "IdleAksClusterPlugin",
    "UnusedAppServicePlansPlugin",
    # Legacy Plugins
    "AzureIdleVMPlugin",
    "AzureUnattachedDisksPlugin",
    "AzureOrphanedImagesPlugin",
    "AzureOrphanedIpsPlugin",
]
