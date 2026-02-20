from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.shared.adapters.feed_utils import parse_timestamp

logger = structlog.get_logger()


def _coerce_token(raw: Any) -> str | None:
    if raw is None:
        return None
    value = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    normalized = value.strip()
    return normalized or None


@registry.register("saas")
class GitHubUnusedSeatPlugin(ZombiePlugin):
    """
    Detects inactive GitHub organization seats.

    Required connector configuration:
    - connector_config.github_org (or connector_config.organization)
    - api_key credential with GitHub token
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
    ) -> list[dict[str, Any]]:
        creds = credentials if isinstance(credentials, dict) else {}
        cfg = config if isinstance(config, dict) else {}
        if not cfg and isinstance(creds.get("connector_config"), dict):
            cfg = creds["connector_config"]

        token = _coerce_token(creds.get("api_key") or cfg.get("github_token"))
        org = (
            str(cfg.get("github_org") or cfg.get("organization") or "").strip()
            or str(creds.get("organization") or "").strip()
        )
        if not token or not org:
            logger.debug("github_plugin_skipped_missing_config")
            return []

        try:
            threshold_days = int(cfg.get("unused_threshold_days", 30))
        except (TypeError, ValueError):
            threshold_days = 30
        try:
            seat_cost = float(cfg.get("seat_cost_usd", 21.0))
        except (TypeError, ValueError):
            seat_cost = 21.0

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                url = f"https://api.github.com/orgs/{org}/members"
                response = await client.get(url, headers=headers)

                if response.status_code != 200:
                    logger.warning(
                        "github_api_failed",
                        status=response.status_code,
                        org=org,
                    )
                    return []

                payload = response.json()
                members = payload if isinstance(payload, list) else payload.get("value", [])
                if not isinstance(members, list):
                    return []

                zombies: list[dict[str, Any]] = []
                now = datetime.now(timezone.utc)
                for member in members:
                    if not isinstance(member, dict):
                        continue
                    username = str(member.get("login") or "").strip()
                    if not username:
                        continue

                    last_active_str = member.get("last_activity")
                    if last_active_str in (None, ""):
                        continue

                    try:
                        last_active = parse_timestamp(last_active_str)
                    except (TypeError, ValueError):
                        continue
                    if last_active.tzinfo is None:
                        last_active = last_active.replace(tzinfo=timezone.utc)

                    days_inactive = (now - last_active).days
                    if days_inactive < threshold_days:
                        continue

                    zombies.append(
                        {
                            "resource_id": username,
                            "resource_type": "GitHub Seat",
                            "resource_name": f"User: {username}",
                            "monthly_cost": seat_cost,
                            "recommendation": "Remove inactive user from organization",
                            "action": "revoke_github_seat",
                            "confidence_score": 0.9,
                            "explainability_notes": (
                                f"User '{username}' inactive for {days_inactive} days "
                                f"(threshold: {threshold_days})."
                            ),
                        }
                    )
                return zombies
        except Exception as exc:  # noqa: BLE001
            logger.error("github_scan_failed", error=str(exc))
            return []
