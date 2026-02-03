"""
GCP Zombie Detection Plugins.

All plugins use billing export data from BigQuery for zero-cost detection.
"""
# New zero-cost plugins (billing export first)
from .compute import IdleVmsPlugin, IdleGpuInstancesPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanExternalIpsPlugin
from .database import IdleCloudSqlPlugin
from .containers import EmptyGkeClusterPlugin, IdleCloudRunPlugin, IdleCloudFunctionsPlugin

# Legacy plugins (for backward compatibility)
from .idle_instances import GCPIdleInstancePlugin
from .unattached_disks import GCPUnattachedDisksPlugin
from .machine_images import GCPMachineImagesPlugin
from .unused_ips import GCPUnusedStaticIpsPlugin

# Alias for backward compatibility
GCPUnusedIpsPlugin = GCPUnusedStaticIpsPlugin

__all__ = [
    # New Zero-Cost Plugins
    "IdleVmsPlugin",
    "IdleGpuInstancesPlugin",
    "UnattachedDisksPlugin",
    "OldSnapshotsPlugin",
    "OrphanExternalIpsPlugin",
    "IdleCloudSqlPlugin",
    "EmptyGkeClusterPlugin",
    "IdleCloudRunPlugin",
    "IdleCloudFunctionsPlugin",
    # Legacy Plugins
    "GCPIdleInstancePlugin",
    "GCPUnattachedDisksPlugin",
    "GCPMachineImagesPlugin",
    "GCPUnusedStaticIpsPlugin",
    "GCPUnusedIpsPlugin",
]
