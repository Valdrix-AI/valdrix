"""
Azure Zombie Detection Plugins.

All plugins use Cost Management export data for zero-cost detection.
"""
from .compute import IdleVmsPlugin, IdleGpuVmsPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanPublicIpsPlugin, OrphanNicsPlugin, OrphanNsgsPlugin
from .database import IdleSqlDatabasesPlugin
from .containers import IdleAksClusterPlugin, UnusedAppServicePlansPlugin

__all__ = [
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
]
