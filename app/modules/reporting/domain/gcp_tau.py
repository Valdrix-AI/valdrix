from typing import Any, Dict, Optional
from app.modules.reporting.domain.arm_analyzer import ArmMigrationAnalyzer

# Mapping of GCP x86 machine types to Tau T2A (ARM) equivalents
# Format: x86_type -> (arm_type, estimated_savings_percent)
TAU_EQUIVALENTS = {
    "n1-standard-1": ("t2a-standard-1", 40),
    "n1-standard-2": ("t2a-standard-2", 40),
    "n1-standard-4": ("t2a-standard-4", 40),
    "n1-standard-8": ("t2a-standard-8", 40),
    "n2-standard-2": ("t2a-standard-2", 35),
    "n2-standard-4": ("t2a-standard-4", 35),
}

class GCPTauAnalyzer(ArmMigrationAnalyzer):
    """
    Analyzes GCP machine types for Tau T2A (ARM) migration opportunities.
    """
    
    def is_arm(self, instance_type: str) -> bool:
        # GCP ARM machine types start with 't2a'
        return instance_type.lower().startswith("t2a-")

    def get_equivalent(self, instance_type: str) -> Optional[tuple[str, int]]:
        return TAU_EQUIVALENTS.get(instance_type)

    def get_instance_type_from_resource(self, resource: Dict[str, Any]) -> Optional[str]:
        # Extracted by GCPAdapter.discover_resources in metadata['machine_type']
        metadata = resource.get("metadata", {})
        return metadata.get("machine_type")
