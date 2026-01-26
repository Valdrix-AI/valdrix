from app.modules.optimization.adapters.azure.plugins.idle_vms import AzureIdleVMPlugin
from app.modules.optimization.adapters.azure.plugins.orphaned_images import AzureOrphanedImagesPlugin
from app.modules.optimization.adapters.azure.plugins.orphaned_ips import AzureOrphanedIpsPlugin
from app.modules.optimization.adapters.azure.plugins.unattached_disks import AzureUnattachedDisksPlugin

__all__ = [
    "AzureIdleVMPlugin",
    "AzureOrphanedImagesPlugin",
    "AzureOrphanedIpsPlugin",
    "AzureUnattachedDisksPlugin",
]
