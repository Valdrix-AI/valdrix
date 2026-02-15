"""
AWS Resource Explorer 2 Adapter (Native Async)

Provides a unified interface for global resource discovery using AWS Resource Explorer 2.
This is significantly faster and cheaper than iterating through all regions and services manually.
"""

from typing import List, Dict, Any
import aioboto3
import structlog
from botocore.exceptions import ClientError
from app.models.aws_connection import AWSConnection
from app.shared.adapters.aws_utils import DEFAULT_BOTO_CONFIG, map_aws_credentials

logger = structlog.get_logger()


class AWSResourceExplorerAdapter:
    """
    Adapter for AWS Resource Explorer 2 to perform account-wide resource searches.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self.session = aioboto3.Session()

    async def _get_client(self) -> Any:
        """Helper to get a configured resource-explorer-2 client."""
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter

        adapter = MultiTenantAWSAdapter(self.connection)
        creds = await adapter.get_credentials()

        return self.session.client(
            "resource-explorer-2",
            region_name=self.connection.region,
            config=DEFAULT_BOTO_CONFIG,
            **map_aws_credentials(creds),
        )

    async def search_resources(
        self, query: str = "*", max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Performs a global search for resources using the aggregator index.

        Args:
            query: The Resource Explorer query string (default '*' for all).
            max_results: Maximum number of resources to return.

        Returns:
            A list of discovered resources with ARN, Service, and Type.
        """
        async with await self._get_client() as client:
            try:
                # 1. Look for the aggregator index first to enable account-wide search
                # In a real-world scenario, we'd list indexes and find the one of type AGGREGATOR
                # For now, we assume search will use the default view if configured properly.

                resources = []
                paginator = client.get_paginator("search")

                async for page in paginator.paginate(
                    QueryString=query,
                    MaxResults=min(max_results, 100),  # Max 100 per page for search
                ):
                    for resource in page.get("Resources", []):
                        resources.append(
                            {
                                "arn": resource["Arn"],
                                "service": resource["Service"],
                                "resource_type": resource["ResourceType"],
                                "region": resource["Region"],
                                "id": resource["Arn"].split("/")[-1]
                                if "/" in resource["Arn"]
                                else resource["Arn"].split(":")[-1],
                            }
                        )
                        if len(resources) >= max_results:
                            break
                    if len(resources) >= max_results:
                        break

                logger.info(
                    "resource_explorer_search_complete",
                    count=len(resources),
                    query=query,
                )
                return resources

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "AccessDeniedException":
                    logger.warning(
                        "resource_explorer_access_denied",
                        account=self.connection.aws_account_id,
                    )
                else:
                    logger.error(
                        "resource_explorer_search_failed", error=str(e), code=error_code
                    )
                return []
            except Exception as e:
                logger.error("resource_explorer_unexpected_error", error=str(e))
                return []

    async def is_enabled(self) -> bool:
        """Checks if Resource Explorer 2 is enabled and has a view."""
        async with await self._get_client() as client:
            try:
                response = await client.list_views()
                return len(response.get("Views", [])) > 0
            except Exception:
                return False
