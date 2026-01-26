from app.modules.optimization.adapters.aws.plugins.storage import UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin
from app.modules.optimization.adapters.aws.plugins.compute import UnusedElasticIpsPlugin, IdleInstancesPlugin
from app.modules.optimization.adapters.aws.plugins.network import OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin
from app.modules.optimization.adapters.aws.plugins.database import IdleRdsPlugin, ColdRedshiftPlugin
from app.modules.optimization.adapters.aws.plugins.analytics import IdleSageMakerPlugin
from app.modules.optimization.adapters.aws.plugins.containers import LegacyEcrImagesPlugin

__all__ = [
    "UnattachedVolumesPlugin",
    "OldSnapshotsPlugin",
    "IdleS3BucketsPlugin",
    "UnusedElasticIpsPlugin",
    "IdleInstancesPlugin",
    "OrphanLoadBalancersPlugin",
    "UnderusedNatGatewaysPlugin",
    "IdleRdsPlugin",
    "ColdRedshiftPlugin",
    "IdleSageMakerPlugin",
    "LegacyEcrImagesPlugin",
]
