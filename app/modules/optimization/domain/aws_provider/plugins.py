from app.modules.optimization.adapters.aws.plugins import (
    UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin,
    UnusedElasticIpsPlugin, IdleInstancesPlugin,
    OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin,
    IdleRdsPlugin, ColdRedshiftPlugin,
    IdleSageMakerPlugin, LegacyEcrImagesPlugin
)

__all__ = [
    "UnattachedVolumesPlugin", "OldSnapshotsPlugin", "IdleS3BucketsPlugin",
    "UnusedElasticIpsPlugin", "IdleInstancesPlugin",
    "OrphanLoadBalancersPlugin", "UnderusedNatGatewaysPlugin",
    "IdleRdsPlugin", "ColdRedshiftPlugin",
    "IdleSageMakerPlugin", "LegacyEcrImagesPlugin"
]
