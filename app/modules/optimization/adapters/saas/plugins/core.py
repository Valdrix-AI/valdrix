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


@registry.register("saas")
class IdleSaaSSubscriptionsPlugin(ZombiePlugin):
    """
    Detect SaaS subscriptions with unused seats or prolonged inactivity.
    """

    @property
    def category_key(self) -> str:
        return "idle_saas_subscriptions"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Dict[str, str] | None = None,
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

            service = str(
                entry.get("service") or entry.get("vendor") or "SaaS Subscription"
            )
            resource_id = str(
                entry.get("subscription_id")
                or entry.get("account_id")
                or entry.get("resource_id")
                or f"saas-{service.lower().replace(' ', '-')}-{index}"
            )
            monthly_cost = _to_float(
                entry.get("cost_usd")
                or entry.get("amount_usd")
                or entry.get("monthly_cost")
                or 0.0
            )
            if monthly_cost <= 0:
                continue

            purchased_seats = _to_int(
                entry.get("purchased_seats") or entry.get("total_seats")
            )
            active_seats = _to_int(
                entry.get("active_seats")
                or entry.get("used_seats")
                or entry.get("active_users")
            )
            status = str(entry.get("status") or "").strip().lower()
            inactive_days = _to_int(
                entry.get("inactive_days") or entry.get("last_activity_days")
            )

            waste = 0.0
            reason = ""
            if (
                purchased_seats
                and active_seats is not None
                and purchased_seats > active_seats
            ):
                unused = purchased_seats - active_seats
                waste = monthly_cost * (unused / purchased_seats)
                reason = f"{unused} unused seats out of {purchased_seats}"
            elif status in {"inactive", "disabled", "cancelled"}:
                waste = monthly_cost
                reason = f"subscription status is {status}"
            elif inactive_days is not None and inactive_days >= 30:
                waste = monthly_cost
                reason = f"no activity for {inactive_days} days"

            if waste <= 0:
                continue

            zombies.append(
                {
                    "resource_id": resource_id,
                    "resource_name": service,
                    "resource_type": "SaaS Subscription",
                    "region": "global",
                    "monthly_cost": round(waste, 2),
                    "monthly_waste": round(waste, 2),
                    "recommendation": "Reduce seats or cancel inactive SaaS subscription",
                    "action": "review_saas_subscription",
                    "confidence_score": 0.85,
                    "explainability_notes": reason,
                }
            )

        return zombies
