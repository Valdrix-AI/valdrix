from abc import ABC, abstractmethod
from typing import Any

import structlog

from app.shared.adapters.base import BaseAdapter

logger = structlog.get_logger()


class ArmMigrationAnalyzer(ABC):
    """Base class for analyzing x86 to ARM migration opportunities."""

    def __init__(self, adapter: BaseAdapter, region: str = "global"):
        self.adapter = adapter
        self.region = region

    @abstractmethod
    def is_arm(self, instance_type: str) -> bool:
        """Return True when the supplied type is already ARM-based."""

    @abstractmethod
    def get_equivalent(self, instance_type: str) -> tuple[str, int] | None:
        """Return (recommended_arm_type, estimated_savings_percent)."""

    @abstractmethod
    def get_instance_type_from_resource(
        self, resource: dict[str, Any]
    ) -> str | None:
        """Extract the provider-specific compute type from a discovered resource."""

    async def analyze(self, tenant_id: Any | None = None) -> dict[str, Any]:
        """Scan compute resources and identify ARM migration candidates."""
        del tenant_id

        try:
            instances = await self.adapter.discover_resources(
                "compute", region=self.region
            )
        except Exception as exc:
            logger.error(
                "arm_analysis_failed",
                error=str(exc),
                provider=getattr(self.adapter, "provider", "unknown"),
                exc_info=True,
            )
            return {
                "total_instances": 0,
                "arm_instances": 0,
                "migration_candidates": 0,
                "candidates": [],
                "error": str(exc),
            }

        if not isinstance(instances, list):
            logger.warning(
                "arm_analysis_invalid_resource_payload",
                payload_type=type(instances).__name__,
                provider=getattr(self.adapter, "provider", "unknown"),
            )
            return {
                "total_instances": 0,
                "arm_instances": 0,
                "migration_candidates": 0,
                "candidates": [],
                "error": "Invalid compute discovery payload",
            }

        candidates: list[dict[str, Any]] = []
        total_instances = 0
        arm_instances = 0

        for inst in instances:
            if not isinstance(inst, dict):
                continue

            total_instances += 1
            instance_type = self.get_instance_type_from_resource(inst)
            if not instance_type:
                continue

            if self.is_arm(instance_type):
                arm_instances += 1
                continue

            equivalent = self.get_equivalent(instance_type)
            if equivalent is None:
                continue

            recommended_type, savings_percent = equivalent
            candidates.append(
                {
                    "resource_id": inst.get("id"),
                    "name": inst.get("name"),
                    "current_type": instance_type,
                    "recommended_type": recommended_type,
                    "savings_percent": savings_percent,
                    "provider": inst.get("provider", "unknown"),
                    "region": inst.get("region", self.region),
                }
            )

        return {
            "total_instances": total_instances,
            "arm_instances": arm_instances,
            "migration_candidates": len(candidates),
            "candidates": candidates,
        }
