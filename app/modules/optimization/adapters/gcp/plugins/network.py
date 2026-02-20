"""
GCP Network Plugins - Zero-Cost Zombie Detection.

Detects orphan external IPs using Compute API (free).
"""

from typing import List, Dict, Any
from google.cloud import compute_v1
from google.oauth2 import service_account
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("gcp")
class OrphanExternalIpsPlugin(ZombiePlugin):
    """Detect unused external IP addresses."""

    @property
    def category_key(self) -> str:
        return "orphan_gcp_ips"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        """Scan for orphan external IPs using Compute API (free)."""
        project_id = str(kwargs.get("project_id") or session or "")
        if not project_id:
            logger.warning("gcp_scan_missing_project_id", plugin=self.category_key)
            return []

        zombies = []

        billing_records = kwargs.get("billing_records")
        if billing_records:
            from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer

            analyzer = GCPUsageAnalyzer(billing_records)
            return analyzer.find_orphan_ips()

        try:
            gcp_creds = None
            if credentials:
                gcp_creds = service_account.Credentials.from_service_account_info(credentials)  # type: ignore[no-untyped-call]
            client = compute_v1.AddressesClient(credentials=gcp_creds)
            request = compute_v1.AggregatedListAddressesRequest(project=project_id)

            for region, response in client.aggregated_list(request=request):
                if not response.addresses:
                    continue

                for address in response.addresses:
                    # RESERVED status means the IP is allocated but not in use
                    if address.status == "RESERVED":
                        region_name = region.split("/")[-1]
                        # External IPs cost ~$0.004/hour when not attached = ~$2.88/month
                        estimated_cost = 2.88

                        zombies.append(
                            {
                                "resource_id": f"projects/{project_id}/regions/{region_name}/addresses/{address.name}",
                                "resource_name": address.name,
                                "resource_type": "External IP Address",
                                "region": region_name,
                                "ip_address": address.address,
                                "monthly_cost": round(estimated_cost, 2),
                                "recommendation": "Release if not needed",
                                "action": "release_ip",
                                "confidence_score": 0.92,
                                "explainability_notes": f"Static IP {address.address} is reserved but not attached to any resource.",
                            }
                        )
        except Exception as e:
            logger.warning("gcp_ip_scan_error", error=str(e))

        return zombies
