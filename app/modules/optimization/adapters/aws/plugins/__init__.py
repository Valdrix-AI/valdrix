from .storage import UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin
from .compute import UnusedElasticIpsPlugin, IdleInstancesPlugin
from .network import OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin
from .database import IdleRdsPlugin, ColdRedshiftPlugin
from .analytics import IdleSageMakerPlugin
from .containers import StaleEcrImagesPlugin

# New high-value and infrastructure plugins
from .high_value import (
    IdleEksPlugin,
    IdleElastiCachePlugin,
    IdleSageMakerNotebooksPlugin,
)
from .infrastructure import (
    StoppedInstancesWithEbsPlugin,
    UnusedLambdaPlugin,
    OrphanVpcEndpointsPlugin,
)

__all__ = [
    # Storage
    "UnattachedVolumesPlugin",
    "OldSnapshotsPlugin",
    "IdleS3BucketsPlugin",
    # Compute
    "UnusedElasticIpsPlugin",
    "IdleInstancesPlugin",
    # Network
    "OrphanLoadBalancersPlugin",
    "UnderusedNatGatewaysPlugin",
    # Database
    "IdleRdsPlugin",
    "ColdRedshiftPlugin",
    # Analytics
    "IdleSageMakerPlugin",
    # Containers
    "StaleEcrImagesPlugin",
    # High-Value (NEW)
    "IdleEksPlugin",
    "IdleElastiCachePlugin",
    "IdleSageMakerNotebooksPlugin",
    # Infrastructure (NEW)
    "StoppedInstancesWithEbsPlugin",
    "UnusedLambdaPlugin",
    "OrphanVpcEndpointsPlugin",
]
