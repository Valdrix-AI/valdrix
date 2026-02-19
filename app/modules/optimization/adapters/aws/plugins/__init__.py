from .storage import UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin, EmptyEfsPlugin
from .compute import UnusedElasticIpsPlugin, IdleInstancesPlugin
from .network import OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin, IdleCloudFrontPlugin
from .database import IdleRdsPlugin, ColdRedshiftPlugin, IdleDynamoDbPlugin
from .analytics import IdleSageMakerPlugin
from .containers import StaleEcrImagesPlugin
from .security import CustomerManagedKeysPlugin
from .search import IdleOpenSearchPlugin
from .rightsizing import OverprovisionedEc2Plugin

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
    "EmptyEfsPlugin",
    # Compute
    "UnusedElasticIpsPlugin",
    "IdleInstancesPlugin",
    # Network
    "OrphanLoadBalancersPlugin",
    "UnderusedNatGatewaysPlugin",
    # Database
    "IdleRdsPlugin",
    "ColdRedshiftPlugin",
    "IdleDynamoDbPlugin",
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
    # Security (NEW)
    "CustomerManagedKeysPlugin",
    # Network (NEW)
    "IdleCloudFrontPlugin",
    "IdleOpenSearchPlugin",
    # Rightsizing (PoC)
    "OverprovisionedEc2Plugin",
]
