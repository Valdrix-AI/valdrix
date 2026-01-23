from .unattached_disks import AzureUnattachedDisksPlugin
from .orphaned_ips import AzureOrphanedIpsPlugin
from .orphaned_images import AzureOrphanedImagesPlugin
from .idle_vms import AzureIdleVMPlugin

__all__ = [
    "AzureUnattachedDisksPlugin",
    "AzureOrphanedIpsPlugin",
    "AzureOrphanedImagesPlugin",
    "AzureIdleVMPlugin",
]
