from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("saas")
class GitHubUnusedSeatPlugin(ZombiePlugin):
    """
    Detects unused GitHub Enterprise seats via API.
    """
    @property
    def category_key(self) -> str:
        return "unused_license_seats"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        zombies = []
        creds = credentials or {}
        token = creds.get("github_token")
        org = creds.get("organization")
        
        if not token or not org:
            logger.debug("github_plugin_skipped_missing_creds")
            return []

        threshold_days = int((config or {}).get("unused_threshold_days", 30))
        seat_cost = float((config or {}).get("seat_cost_usd", 21.0)) # GitHub Enterprise ~$21/mo

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        try:
            async with httpx.AsyncClient() as client:
                # 1. List Organization Members
                # Pagination required in production, simplified here
                url = f"https://api.github.com/orgs/{org}/members"
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    logger.warning("github_api_failed", status=response.status_code)
                    return []
                
                members = response.json()
                for member in members:
                    username = member.get("login")
                    # Check activity (simplified - usually requires audit log or events API)
                    # For MVP, we use 'last_activity' if available in enhanced mock/response
                    # Real GitHub API doesn't return last_activity in basic /members list clearly without SAML/SCIM
                    # Assuming we query Audit Log or SCIM for 'last_active'
                    
                    last_active_str = member.get("last_activity")
                    if not last_active_str:
                        continue 

                    try:
                        last_active = datetime.fromisoformat(last_active_str.replace("Z", "+00:00"))
                        days_inactive = (datetime.now(last_active.tzinfo) - last_active).days
                        
                        if days_inactive >= threshold_days:
                            zombies.append({
                                "resource_id": username,
                                "resource_type": "GitHub Seat",
                                "resource_name": f"User: {username}",
                                "monthly_cost": seat_cost,
                                "recommendation": "Remove inactive user from organization",
                                "action": "revoke_github_seat",
                                "confidence_score": 0.9,
                                "explainability_notes": f"User '{username}' inactive for {days_inactive} days (Threshold: {threshold_days})."
                            })
                    except ValueError:
                        pass

        except Exception as e:
            logger.error("github_scan_failed", error=str(e))

        return zombies
