from typing import Any, Dict, List

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@registry.register("hybrid")
class IdleHybridResourcesPlugin(ZombiePlugin):
    """
    Detect idle/underutilized private or hybrid infrastructure resources.
    """

    @property
    def category_key(self) -> str:
        return "idle_hybrid_resources"

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        cost_feed = kwargs.get("cost_feed") or []
        if not isinstance(cost_feed, list):
            return []

        zombies: List[Dict[str, Any]] = []
        for index, entry in enumerate(cost_feed):
            if not isinstance(entry, dict):
                continue

            service = str(entry.get("service") or entry.get("vendor") or "Hybrid Infra")
            resource_id = str(
                entry.get("resource_id")
                or entry.get("host_id")
                or entry.get("instance_id")
                or f"hybrid-{service.lower().replace(' ', '-')}-{index}"
            )
            monthly_cost = _to_float(
                entry.get("cost_usd")
                or entry.get("amount_usd")
                or entry.get("monthly_cost")
                or 0.0
            )
            if monthly_cost <= 0:
                continue

            allocated_units = _to_int(
                entry.get("allocated_units")
                or entry.get("allocated_cpu")
                or entry.get("capacity_units")
            )
            active_units = _to_int(
                entry.get("active_units")
                or entry.get("used_units")
                or entry.get("used_cpu")
            )
            utilization_pct = _to_float(
                entry.get("utilization_pct")
                or entry.get("cpu_utilization_pct")
                or entry.get("utilization"),
                default=-1.0,
            )
            status = str(entry.get("status") or "").strip().lower()

            waste = 0.0
            reason = ""
            if (
                allocated_units
                and active_units is not None
                and allocated_units > active_units
            ):
                unused = allocated_units - active_units
                waste = monthly_cost * (unused / allocated_units)
                reason = f"{unused} unused units out of {allocated_units}"
            elif 0 <= utilization_pct <= 25:
                waste = monthly_cost * max(0.0, 1 - (utilization_pct / 100.0))
                reason = f"utilization is {utilization_pct:.1f}%"
            elif status in {"inactive", "shutdown", "retired"}:
                waste = monthly_cost
                reason = f"resource status is {status}"

            if waste <= 0:
                continue

            zombies.append(
                {
                    "resource_id": resource_id,
                    "resource_name": service,
                    "resource_type": "Hybrid Resource",
                    "region": "global",
                    "monthly_cost": round(waste, 2),
                    "monthly_waste": round(waste, 2),
                    "recommendation": "Review utilization and decommission idle hybrid resources",
                    "action": "manual_review",
                    "confidence_score": 0.82,
                    "explainability_notes": reason,
                }
            )

        return zombies
