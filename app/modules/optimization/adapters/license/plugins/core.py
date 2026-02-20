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


@registry.register("license")
class UnusedLicenseSeatsPlugin(ZombiePlugin):
    """
    Detect license contracts with unused seats or inactive status.
    """

    @property
    def category_key(self) -> str:
        return "unused_license_seats"

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

            service = str(entry.get("service") or entry.get("vendor") or "License")
            resource_id = str(
                entry.get("license_id")
                or entry.get("contract_id")
                or entry.get("resource_id")
                or f"license-{service.lower().replace(' ', '-')}-{index}"
            )
            monthly_cost = _to_float(
                entry.get("cost_usd")
                or entry.get("amount_usd")
                or entry.get("monthly_cost")
                or 0.0
            )
            if monthly_cost <= 0:
                continue

            purchased = _to_int(
                entry.get("purchased_seats") or entry.get("total_seats")
            )
            assigned = _to_int(
                entry.get("assigned_seats")
                or entry.get("used_seats")
                or entry.get("active_users")
            )
            status = str(entry.get("status") or "").strip().lower()

            waste = 0.0
            reason = ""
            if purchased and assigned is not None and purchased > assigned:
                unused = purchased - assigned
                waste = monthly_cost * (unused / purchased)
                reason = f"{unused} unused licenses out of {purchased}"
            elif status in {"inactive", "expired", "cancelled"}:
                waste = monthly_cost
                reason = f"license status is {status}"

            if waste <= 0:
                continue

            zombies.append(
                {
                    "resource_id": resource_id,
                    "resource_name": service,
                    "resource_type": "License Contract",
                    "region": "global",
                    "monthly_cost": round(waste, 2),
                    "monthly_waste": round(waste, 2),
                    "recommendation": "Reclaim unused licenses or renegotiate contract",
                    "action": "review_license_contract",
                    "confidence_score": 0.9,
                    "explainability_notes": reason,
                }
            )

        return zombies
