"""DB-backed cloud pricing service."""

import structlog
from typing import Any

from app.shared.core.cloud_pricing_data import (
    get_cloud_hourly_rate,
    sync_supported_aws_pricing,
)

logger = structlog.get_logger()


class PricingService:
    """
    Standardized pricing engine.
    """

    @staticmethod
    def get_hourly_rate(
        provider: str,
        resource_type: str,
        resource_size: str | None = None,
        region: str = "global",
    ) -> float:
        """
        Returns the hourly rate for a resource.
        """
        final_rate = get_cloud_hourly_rate(
            provider=provider,
            resource_type=resource_type,
            resource_size=resource_size,
            region=region,
        )
        if final_rate == 0.0:
            logger.debug(
                "pricing_missing",
                provider=provider,
                type=resource_type,
                size=resource_size,
                region=region,
            )

        return final_rate

    @staticmethod
    async def sync_with_aws(db_session: Any = None, *, client: Any = None) -> int:
        """Persist supported AWS Pricing API observations into the cloud pricing catalog."""
        return await sync_supported_aws_pricing(db_session=db_session, client=client)

    @staticmethod
    def estimate_monthly_waste(
        provider: str,
        resource_type: str,
        resource_size: str | None = None,
        region: str = "global",
        quantity: float = 1.0,
    ) -> float:
        """Estimates monthly waste based on hourly rates."""
        hourly = PricingService.get_hourly_rate(
            provider, resource_type, resource_size, region
        )
        return hourly * 730 * quantity  # 730 hours in a month (Industry Average)
