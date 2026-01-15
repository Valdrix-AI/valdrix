from .storage import UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin
from .compute import UnusedElasticIpsPlugin, IdleInstancesPlugin
from .network import OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin
from .database import IdleRdsPlugin, ColdRedshiftPlugin
from .analytics import IdleSageMakerPlugin
from .containers import LegacyEcrImagesPlugin

__all__ = [
    "UnattachedVolumesPlugin", "OldSnapshotsPlugin", "IdleS3BucketsPlugin",
    "UnusedElasticIpsPlugin", "IdleInstancesPlugin",
    "OrphanLoadBalancersPlugin", "UnderusedNatGatewaysPlugin",
    "IdleRdsPlugin", "ColdRedshiftPlugin",
    "IdleSageMakerPlugin",
    "LegacyEcrImagesPlugin",
]
