"""
GCP Zombie Detection Plugins.

All plugins use billing export data from BigQuery for zero-cost detection.
"""

from .compute import IdleVmsPlugin, IdleGpuInstancesPlugin, StoppedVmsPlugin
from .storage import UnattachedDisksPlugin, OldSnapshotsPlugin
from .network import OrphanExternalIpsPlugin
from .database import IdleCloudSqlPlugin
from .containers import (
    EmptyGkeClusterPlugin,
    IdleCloudRunPlugin,
    IdleCloudFunctionsPlugin,
)
from .ai import IdleVertexEndpointsPlugin
from .search import IdleVectorSearchPlugin
from .rightsizing import OverprovisionedComputePlugin

__all__ = [
    "IdleVmsPlugin",
    "IdleGpuInstancesPlugin",
    "StoppedVmsPlugin",
    "IdleVertexEndpointsPlugin",
    "IdleVectorSearchPlugin",
    "OverprovisionedComputePlugin",
    "UnattachedDisksPlugin",
    "OldSnapshotsPlugin",
    "OrphanExternalIpsPlugin",
    "IdleCloudSqlPlugin",
    "EmptyGkeClusterPlugin",
    "IdleCloudRunPlugin",
    "IdleCloudFunctionsPlugin",
]
