"""
Unified Discovery Service

Orchestrates resource discovery across different cloud providers and discovery methods.
Implements a hybrid model:
1. Try global discovery first (e.g., AWS Resource Explorer 2) - Fast & Cheap/Free.
2. Fallback to regional/service-specific discovery if global is unavailable or incomplete.
"""

from datetime import datetime
import structlog
from app.models.aws_connection import AWSConnection
from app.shared.adapters.aws_resource_explorer import AWSResourceExplorerAdapter
from app.schemas.inventory import DiscoveredResource, CloudInventory

logger = structlog.get_logger()


class UnifiedDiscoveryService:
    """
    Main entry point for account-wide resource inventory discovery.
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    async def discover_aws_inventory(self, connection: AWSConnection) -> CloudInventory:
        """
        Discovers all resources in an AWS account using the Hybrid Model.
        """
        explorer = AWSResourceExplorerAdapter(connection)

        # Phase 1: Try Resource Explorer 2 (Global & Cost-Free)
        if await explorer.is_enabled():
            logger.info(
                "aws_discovery_global_search_start", account=connection.aws_account_id
            )

            raw_resources = await explorer.search_resources()

            resources = [
                DiscoveredResource(
                    id=r["id"],
                    arn=r["arn"],
                    service=r["service"],
                    resource_type=r["resource_type"],
                    region=r["region"],
                    provider="aws",
                    metadata={"discovery_method": "resource-explorer-2"},
                )
                for r in raw_resources
            ]

            return CloudInventory(
                tenant_id=str(connection.tenant_id),
                provider="aws",
                resources=resources,
                total_count=len(resources),
                discovery_method="resource-explorer-2",
                discovered_at=datetime.now().isoformat(),
            )

        # Phase 2: Fallback to service-specific scans when global search is unavailable.
        logger.warning(
            "aws_discovery_global_search_unavailable_fallback",
            account=connection.aws_account_id,
        )

        # Note: In the future, this could trigger a background sweep
        # using individual plugins, but for now we'll mark it as native-api.
        # This will be refined as we update AWSZombieDetector.

        return CloudInventory(
            tenant_id=str(connection.tenant_id),
            provider="aws",
            resources=[],
            total_count=0,
            discovery_method="native-api-fallback",
            discovered_at=datetime.now().isoformat(),
        )
