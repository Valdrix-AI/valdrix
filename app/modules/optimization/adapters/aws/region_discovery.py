"""
Dynamic AWS Region Discovery

Implements the 2026 best practice of dynamic region discovery:
1. Phase 1: Get enabled regions via EC2 describe_regions
2. Phase 2: Filter by activity via Cost Explorer GetDimensionValues

This replaces hardcoded region lists and optimizes API calls by only
scanning regions with actual resources/costs.
"""

import aioboto3
from datetime import date, timedelta
from typing import List, Dict
import structlog
from botocore.exceptions import ClientError
from botocore.session import get_session

logger = structlog.get_logger()


class RegionDiscovery:
    """
    Dynamically discovers AWS regions based on account configuration and activity.

    Use `get_hot_regions()` for daily scans (regions with recent costs).
    Use `get_enabled_regions()` for weekly scans (catch new deployments).
    """

    def __init__(self, credentials: Dict[str, str] = None):
        self.credentials = credentials
        self.session = aioboto3.Session()
        self._cached_enabled_regions: List[str] = []
        self._cached_hot_regions: List[str] = []

    def _build_client_kwargs(self, context: str) -> Dict[str, str] | None:
        if not self.credentials:
            return {}
        if not isinstance(self.credentials, dict):
            logger.warning("aws_credentials_invalid_type", context=context, type=type(self.credentials).__name__)
            return None

        ak = self.credentials.get("AccessKeyId")
        sk = self.credentials.get("SecretAccessKey")
        st = self.credentials.get("SessionToken")

        if not ak or not sk:
            logger.warning(
                "invalid_aws_credentials_keys",
                context=context,
                has_ak=bool(ak),
                has_sk=bool(sk)
            )
            return None

        return {
            "aws_access_key_id": ak,
            "aws_secret_access_key": sk,
            "aws_session_token": st,
        }

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

            async with self.session.client("ec2", region_name="us-east-1", **client_kwargs) as ec2:
                response = await ec2.describe_regions(AllRegions=False)
                regions = [
                    r.get("RegionName")
                    for r in response.get("Regions", [])
                    if r.get("RegionName")
                ]

                if not regions:
                    logger.warning("regions_discovered_empty", source="ec2_describe_regions")
                    return self._get_fallback_regions()

                logger.info("regions_discovered", count=len(regions), source="ec2_describe_regions")
                self._cached_enabled_regions = regions
                return regions

        except ClientError as e:
            logger.error("region_discovery_failed", error=str(e))
            # Fallback to common regions if discovery fails
            return self._get_fallback_regions()
        except Exception as e:
            logger.error("region_discovery_unexpected_error", error=str(e))
            return self._get_fallback_regions()

    async def get_hot_regions(self, days: int = 30) -> List[str]:
        """
        Get regions with recent cost activity (last N days).

        Uses Cost Explorer GetDimensionValues to find regions
        with >$0 spend. This optimizes scanning by skipping empty regions.
        """
        if self._cached_hot_regions:
            return self._cached_hot_regions

        try:
            if days <= 0:
                logger.warning("hot_region_invalid_days", days=days)
                return await self.get_enabled_regions()

            client_kwargs = self._build_client_kwargs("hot_regions")
            if client_kwargs is None:
                return await self.get_enabled_regions()

            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            async with self.session.client("ce", region_name="us-east-1", **client_kwargs) as ce:
                response = await ce.get_dimension_values(
                    TimePeriod={
                        "Start": start_date.isoformat(),
                        "End": end_date.isoformat()
                    },
                    Dimension="REGION",
                    Context="COST_AND_USAGE"
                )

                regions = [
                    dv.get("Value")
                    for dv in response.get("DimensionValues", [])
                    if dv.get("Value")
                ]

                logger.info("hot_regions_discovered",
                           count=len(regions),
                           days=days,
                           source="cost_explorer")

                if not regions:
                    logger.warning("hot_regions_discovered_empty", days=days)
                    return await self.get_enabled_regions()

                self._cached_hot_regions = regions
                return regions

        except ClientError as e:
            logger.warning("hot_region_discovery_failed", error=str(e))
            # Fall back to enabled regions
            return await self.get_enabled_regions()
        except Exception as e:
            logger.warning("hot_region_discovery_unexpected_error", error=str(e))
            return await self.get_enabled_regions()

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
        self._cached_hot_regions = []
