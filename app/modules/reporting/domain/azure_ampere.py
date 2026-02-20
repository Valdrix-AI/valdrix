from typing import Any, Dict, Optional
from app.modules.reporting.domain.arm_analyzer import ArmMigrationAnalyzer

# Mapping of Azure x86 VM sizes to Ampere Altra (ARM) equivalents
# Format: x86_size -> (arm_size, estimated_savings_percent)
AMPERE_EQUIVALENTS = {
    # General Purpose
    "Standard_D2s_v5": ("Standard_D2ps_v5", 40),
    "Standard_D4s_v5": ("Standard_D4ps_v5", 40),
    "Standard_D8s_v5": ("Standard_D8ps_v5", 40),
    "Standard_D16s_v5": ("Standard_D16ps_v5", 40),
    # Memory Optimized
    "Standard_E2s_v5": ("Standard_E2ps_v5", 40),
    "Standard_E4s_v5": ("Standard_E4ps_v5", 40),
    "Standard_E8s_v5": ("Standard_E8ps_v5", 40),
}

class AzureAmpereAnalyzer(ArmMigrationAnalyzer):
    """
    Analyzes Azure VM sizes for Ampere Altra (ARM) migration opportunities.
    """
    
    def is_arm(self, instance_type: str) -> bool:
        # Azure ARM VM sizes typically contain 'p' (e.g., Dpsv5, Epsv5)
        # and are often 'v5' series currently.
        return "ps_v5" in instance_type.lower() or "pdsv5" in instance_type.lower()

    def get_equivalent(self, instance_type: str) -> Optional[tuple[str, int]]:
        return AMPERE_EQUIVALENTS.get(instance_type)

    def get_instance_type_from_resource(self, resource: Dict[str, Any]) -> Optional[str]:
        # Extracted by AzureAdapter.discover_resources in metadata['size']
        metadata: Dict[str, Any] = resource.get("metadata", {})
        size = metadata.get("size")
        return str(size) if size else None
