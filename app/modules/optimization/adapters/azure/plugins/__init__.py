"""
Azure Zombie Detection Plugins.

All plugins use Cost Management export data for zero-cost detection.
"""

from .compute import IdleVmsPlugin, IdleGpuVmsPlugin, StoppedVmsPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanPublicIpsPlugin, OrphanNicsPlugin, OrphanNsgsPlugin
from .database import IdleSqlDatabasesPlugin
from .containers import IdleAksClusterPlugin, UnusedAppServicePlansPlugin
from .ai import IdleAzureOpenAIPlugin, IdleAISearchPlugin
from .rightsizing import OverprovisionedVmPlugin

__all__ = [
    "IdleVmsPlugin",
    "IdleGpuVmsPlugin",
    "StoppedVmsPlugin",
    "StoppedVmsPlugin",
    "UnattachedDisksPlugin",
    "OldSnapshotsPlugin",
    "OrphanPublicIpsPlugin",
    "OrphanNicsPlugin",
    "OrphanNsgsPlugin",
    "IdleSqlDatabasesPlugin",
    "IdleAksClusterPlugin",
    "UnusedAppServicePlansPlugin",
    "IdleAzureOpenAIPlugin",
    "IdleAISearchPlugin",
    "OverprovisionedVmPlugin",
]
