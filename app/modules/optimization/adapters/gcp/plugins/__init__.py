"""
GCP Zombie Detection Plugins.

All plugins use billing export data from BigQuery for zero-cost detection.
"""
from .compute import IdleVmsPlugin, IdleGpuInstancesPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanExternalIpsPlugin
from .database import IdleCloudSqlPlugin
from .containers import EmptyGkeClusterPlugin, IdleCloudRunPlugin, IdleCloudFunctionsPlugin

__all__ = [
    "IdleVmsPlugin",
    "IdleGpuInstancesPlugin",
    "UnattachedDisksPlugin",
    "OldSnapshotsPlugin",
    "OrphanExternalIpsPlugin",
    "IdleCloudSqlPlugin",
    "EmptyGkeClusterPlugin",
    "IdleCloudRunPlugin",
    "IdleCloudFunctionsPlugin",
]
