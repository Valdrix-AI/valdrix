"""
Azure Network Plugins - Zero-Cost Zombie Detection.

Detects orphan public IPs, NICs, and NSGs using Azure Resource Graph (free).
"""

from typing import List, Dict, Any
from azure.mgmt.network.aio import NetworkManagementClient
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("azure")
class OrphanPublicIpsPlugin(ZombiePlugin):
    """Detect unused Public IP addresses."""

    @property
    def category_key(self) -> str:
        return "orphan_azure_ips"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Any = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for orphan public IPs using Network API (free)."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        zombies = []

        cost_records = kwargs.get("cost_records")
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_orphan_public_ips()

        try:
            client = NetworkManagementClient(credentials, subscription_id)

            async for ip in client.public_ip_addresses.list_all():
                # Public IP is orphan if ip_configuration is None
                if ip.ip_configuration is None:
                    # Static IPs: ~$0.005/hour = ~$3.65/month
                    # Basic SKU is cheaper, Standard is more expensive
                    estimated_cost = (
                        5.0 if ip.sku and ip.sku.name == "Standard" else 3.65
                    )

                    zombies.append(
                        {
                            "resource_id": ip.id,
                            "resource_name": ip.name,
                            "resource_type": "Public IP Address",
                            "location": ip.location,
                            "ip_address": ip.ip_address,
                            "sku": ip.sku.name if ip.sku else "Basic",
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Delete if not needed",
                            "action": "delete_ip",
                            "confidence_score": 0.92,
                            "explainability_notes": f"Public IP {ip.ip_address or 'not allocated'} is not associated with any resource.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_ip_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class OrphanNicsPlugin(ZombiePlugin):
    """Detect Network Interfaces not attached to any VM."""

    @property
    def category_key(self) -> str:
        return "orphan_azure_nics"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Any = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for orphan NICs."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        zombies = []

        try:
            client = NetworkManagementClient(credentials, subscription_id)

            async for nic in client.network_interfaces.list_all():
                # NIC is orphan if virtual_machine is None
                if nic.virtual_machine is None:
                    zombies.append(
                        {
                            "resource_id": nic.id,
                            "resource_name": nic.name,
                            "resource_type": "Network Interface",
                            "location": nic.location,
                            "monthly_cost": 0.0,  # NICs are free
                            "recommendation": "Delete to clean up resources",
                            "action": "delete_nic",
                            "confidence_score": 0.88,
                            "explainability_notes": "Network Interface is not attached to any VM. Delete to reduce clutter.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_nic_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class OrphanNsgsPlugin(ZombiePlugin):
    """Detect Network Security Groups not associated with any subnet or NIC."""

    @property
    def category_key(self) -> str:
        return "orphan_azure_nsgs"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Any = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Scan for orphan NSGs."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        zombies = []

        try:
            client = NetworkManagementClient(credentials, subscription_id)

            async for nsg in client.network_security_groups.list_all():
                # NSG is orphan if not associated with any NIC or subnet
                is_orphan = (not nsg.network_interfaces) and (not nsg.subnets)

                if is_orphan:
                    zombies.append(
                        {
                            "resource_id": nsg.id,
                            "resource_name": nsg.name,
                            "resource_type": "Network Security Group",
                            "location": nsg.location,
                            "monthly_cost": 0.0,  # NSGs are free
                            "recommendation": "Delete to clean up resources",
                            "action": "delete_nsg",
                            "confidence_score": 0.80,
                            "explainability_notes": "Network Security Group is not associated with any NIC or subnet.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_nsg_scan_error", error=str(e))

        return zombies
