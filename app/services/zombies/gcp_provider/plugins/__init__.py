from .unattached_disks import GCPUnattachedDisksPlugin
from .unused_ips import GCPUnusedStaticIpsPlugin
from .machine_images import GCPMachineImagesPlugin
from .idle_instances import GCPIdleInstancePlugin

__all__ = [
    "GCPUnattachedDisksPlugin",
    "GCPUnusedStaticIpsPlugin",
    "GCPMachineImagesPlugin",
    "GCPIdleInstancePlugin",
]
