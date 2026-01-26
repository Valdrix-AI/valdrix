from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin
from app.modules.optimization.adapters.gcp.plugins.unattached_disks import GCPUnattachedDisksPlugin
from app.modules.optimization.adapters.gcp.plugins.machine_images import GCPMachineImagesPlugin
from app.modules.optimization.adapters.gcp.plugins.unused_ips import GCPUnusedStaticIpsPlugin

# For backward compatibility with tests
GCPUnusedIpsPlugin = GCPUnusedStaticIpsPlugin

__all__ = [
    "GCPIdleInstancePlugin",
    "GCPUnattachedDisksPlugin",
    "GCPMachineImagesPlugin",
    "GCPUnusedStaticIpsPlugin",
    "GCPUnusedIpsPlugin",
]
