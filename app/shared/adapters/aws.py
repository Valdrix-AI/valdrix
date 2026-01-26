from typing import List, Dict, Any
from datetime import date, datetime, timezone
from decimal import Decimal
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.shared.core.config import get_settings
from app.shared.adapters.base import CostAdapter

logger = structlog.get_logger()

class AWSAdapter(CostAdapter):
    def __init__(self):
        # We don't hardcode keys! We rely on environment variables (AWS_ACCESS_KEY_ID, etc.)
        # boto3 automatically looks for them in os.environ.
        self.settings = get_settings()
        # Create session
        self.session = aioboto3.Session()

    async def verify_connection(self) -> bool:
        """
        Verify that the provided AWS credentials have the necessary permissions.
        Currently returns True to satisfy the interface; actual validation occurs
        during the first Cost Explorer call.
        """
        return True

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Standardized interface for cost collection."""
        return await self.get_daily_costs(start_date.date(), end_date.date())

    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """Legacy adapter resource discovery."""
        return []

    async def get_daily_costs(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Fetches daily unblended costs from AWS Cost Explorer.

        Args:
            start_date (date): ISO 8601 start date (e.g., 2026-01-01).
            end_date (date): ISO 8601 end date.

        Returns:
            List[Dict[str, Any]]: The 'ResultsByTime' list from the AWS CE API response.
            Returns an empty list [] provided errors occur (e.g. invalid permissions),
            ensuring the app doesn't crash.
        """
        try:
            # AWS requires strings in 'YYYY-MM-DD' format
            async with self.session.client(
                "ce",
                region_name=self.settings.AWS_DEFAULT_REGION,
                aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY
            ) as client:
                response = await client.get_cost_and_usage(
                    TimePeriod={
                        'Start': start_date.isoformat(),
                        'End': end_date.isoformat(),
                    },
                    Granularity='DAILY',
                    Metrics=['UnblendedCost'],
                )
                logger.info("AWS Cost Explorer response", response=response)
                return response.get("ResultsByTime", [])

        except ClientError as e:
            from app.shared.core.exceptions import AdapterError
            raise AdapterError(
                message="AWS Cost Explorer fetch failed",
                code=e.response.get("Error", {}).get("Code", "Unknown"),
                details={"error": str(e)}
            ) from e



    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        """
        Stream cost data from AWS Cost Explorer.
        """
        results = await self.get_daily_costs(start_date.date(), end_date.date())
        for result in results:
            dt = datetime.fromisoformat(result["TimePeriod"]["Start"]).replace(tzinfo=timezone.utc)
            if "Total" in result:
                amount = Decimal(result["Total"]["UnblendedCost"]["Amount"])
                yield {
                    "timestamp": dt,
                    "service": "Total",
                    "region": self.settings.AWS_DEFAULT_REGION,
                    "cost_usd": amount,
                    "currency": "USD",
                    "amount_raw": amount,
                    "usage_type": "Usage"
                }

    async def get_resource_usage(self, service_name: str, resource_id: str = None) -> List[Dict[str, Any]]:
        """
        Optional: Fetch granular usage metrics for a specific resource.
        Not implemented for the base AWS adapter.
        """
        return []
