from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import structlog
from app.shared.adapters.factory import AdapterFactory

logger = structlog.get_logger()

class ArmMigrationAnalyzer(ABC):
    """
    Base class for analyzing x86 to ARM migration opportunities.
    """
    
    def __init__(self, connection: Any, region: str = "global"):
        self.connection = connection
        self.region = region
        self.adapter = AdapterFactory.get_adapter(connection)

    @abstractmethod
    def is_arm(self, instance_type: str) -> bool:
        """Check if an instance type is already ARM-based."""

    @abstractmethod
    def get_equivalent(self, instance_type: str) -> Optional[tuple[str, int]]:
        """Get the ARM equivalent and estimated savings percentage."""

    @abstractmethod
    def get_instance_type_from_resource(self, resource: Dict[str, Any]) -> Optional[str]:
        """Extract instance type/size from discovery metadata."""

    async def analyze(self) -> Dict[str, Any]:
        """Generic analysis flow for compute resources."""
        try:
            # Discover compute resources
            instances = await self.adapter.discover_resources("compute", region=self.region)
            
            candidates = []
            total_instances = 0
            arm_instances = 0

            for inst in instances:
                total_instances += 1
                instance_type = self.get_instance_type_from_resource(inst)
                
                if not instance_type:
                    continue

                if self.is_arm(instance_type):
                    arm_instances += 1
                    continue

                equiv = self.get_equivalent(instance_type)
                if equiv:
                    recommended_type, savings = equiv
                    candidates.append({
                        "resource_id": inst.get("id"),
                        "name": inst.get("name"),
                        "current_type": instance_type,
                        "recommended_type": recommended_type,
                        "savings_percent": savings,
                        "provider": inst.get("provider", "unknown"),
                        "region": inst.get("region", self.region),
                    })

            return {
                "total_instances": total_instances,
                "arm_instances": arm_instances,
                "migration_candidates": len(candidates),
                "candidates": candidates,
            }
        except Exception as e:
            logger.error("arm_analysis_failed", error=str(e), provider=getattr(self.connection, "provider", "unknown"))
            # Re-raise or return error dict
            return {
                "total_instances": 0,
                "arm_instances": 0,
                "migration_candidates": 0,
                "error": str(e)
            }
