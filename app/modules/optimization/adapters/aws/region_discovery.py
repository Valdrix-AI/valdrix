"""
Dynamic AWS Region Discovery

Implements dynamic region discovery:
1. Phase 1: Try AWS Resource Explorer 2 (Global & Cost-Free) to find active regions.
2. Phase 2: Fallback to EC2 describe_regions (Enabled Regions) if Resource Explorer is unavailable.
3. Phase 3: Filter by configuration (if applied later).

This replaces hardcoded region lists and optimizes API calls.
"""

import aioboto3
from typing import Dict, List, TYPE_CHECKING
import structlog
from botocore.exceptions import ClientError
from botocore.session import get_session

if TYPE_CHECKING:
    from app.models.aws_connection import AWSConnection

logger = structlog.get_logger()


class RegionDiscovery:
    """
    Dynamically discovers AWS regions based on account configuration.

    Use `get_active_regions()` for the smartest scan list.
    """

    def __init__(
        self,
        credentials: Dict[str, str] | None = None,
        connection: "AWSConnection | None" = None,
    ):
        self.credentials = credentials
        self.connection = connection
        self.session = aioboto3.Session()
        self._cached_enabled_regions: List[str] = []
        self._cached_active_regions: List[str] = []

    def _build_client_kwargs(self, context: str) -> Dict[str, str] | None:
        if not self.credentials:
            return {}
        if not isinstance(self.credentials, dict):
            logger.warning(
                "aws_credentials_invalid_type",
                context=context,
                type=type(self.credentials).__name__,
            )
            return None

        ak = self.credentials.get("AccessKeyId")
        sk = self.credentials.get("SecretAccessKey")
        st = self.credentials.get("SessionToken")

        if not ak or not sk:
            logger.warning(
                "invalid_aws_credentials_keys",
                context=context,
                has_ak=bool(ak),
                has_sk=bool(sk),
            )
            return None

        kwargs: Dict[str, str] = {
            "aws_access_key_id": ak,
            "aws_secret_access_key": sk,
        }
        if st:
            kwargs["aws_session_token"] = st
        return kwargs

    async def get_active_regions(self) -> List[str]:
        """
        Get 'active' regions using Resource Explorer 2 if available.
        Falls back to 'enabled' regions if RE2 is disabled or fails.
        """
        if self._cached_active_regions:
            return self._cached_active_regions

        # Phase 1: Try Resource Explorer 2
        if self.connection:
            try:
                from app.shared.adapters.aws_resource_explorer import (
                    AWSResourceExplorerAdapter,
                )

                explorer = AWSResourceExplorerAdapter(self.connection)
                if await explorer.is_enabled():
                    # Search for any resource to identify active regions
                    # We group by region to get a unique list
                    resources = await explorer.search_resources(
                        query="region:*", max_results=500
                    )
                    active_regions = sorted(
                        list(set(r.get("region") for r in resources if r.get("region")))
                    )

                    if active_regions:
                        logger.info(
                            "active_regions_discovered_via_re2",
                            count=len(active_regions),
                            regions=active_regions,
                        )
                        self._cached_active_regions = active_regions
                        return active_regions
            except Exception as e:
                logger.warning(
                    "resource_explorer_discovery_failed",
                    error=str(e),
                    account=self.connection.aws_account_id,
                )

        # Phase 2: Fallback to Enabled Regions (EC2)
        return await self.get_enabled_regions()

    async def get_enabled_regions(self) -> List[str]:
        """
        Get all regions enabled for this account.

        Uses EC2 describe_regions with AllRegions=False to only get
        regions that are enabled (default + manually opted-in).
        """
        if self._cached_enabled_regions:
            return self._cached_enabled_regions

        try:
            client_kwargs = self._build_client_kwargs("enabled_regions")
            if client_kwargs is None:
                return self._get_fallback_regions()

            async with self.session.client(
                "ec2", region_name="us-east-1", **client_kwargs
            ) as ec2:
                response = await ec2.describe_regions(AllRegions=False)
                regions = [
                    r.get("RegionName")
                    for r in response.get("Regions", [])
                    if r.get("RegionName")
                ]

                if not regions:
                    logger.warning(
                        "regions_discovered_empty", source="ec2_describe_regions"
                    )
                    return self._get_fallback_regions()

                logger.info(
                    "regions_discovered",
                    count=len(regions),
                    source="ec2_describe_regions",
                )
                self._cached_enabled_regions = regions
                return regions

        except ClientError as e:
            logger.error("region_discovery_failed", error=str(e))
            # Fallback to common regions if discovery fails
            return self._get_fallback_regions()
        except Exception as e:
            logger.error("region_discovery_unexpected_error", error=str(e))
            return self._get_fallback_regions()

    def _get_fallback_regions(self) -> List[str]:
        """Fallback region list when API-based discovery fails."""
        try:
            regions = get_session().get_available_regions("ec2")
            if regions:
                return sorted(set(regions))
        except Exception as exc:
            logger.warning("region_fallback_from_botocore_failed", error=str(exc))

        # Last-resort static baseline
        return [
            "us-east-1",
            "us-west-2",
            "eu-west-1",
            "eu-central-1",
            "ap-southeast-1",
            "ap-northeast-1",
        ]

    def clear_cache(self) -> None:
        """Clear cached regions (useful for testing or forced refresh)."""
        self._cached_enabled_regions = []
        self._cached_active_regions = []
