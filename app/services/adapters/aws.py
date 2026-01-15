from typing import List, Dict, Any
from datetime import date
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.core.config import get_settings
from app.services.adapters.base import CostAdapter

logger = structlog.get_logger()

class AWSAdapter(CostAdapter):
    def __init__(self):
        # We don't hardcode keys! We rely on environment variables (AWS_ACCESS_KEY_ID, etc.)
        # boto3 automatically looks for them in os.environ.
        self.settings = get_settings()
        # Create session
        self.session = aioboto3.Session()

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
            from app.core.exceptions import AdapterError
            raise AdapterError(
                message="AWS Cost Explorer fetch failed",
                code=e.response.get("Error", {}).get("Code", "Unknown"),
                details={"error": str(e)}
            ) from e



    async def get_resource_usage(self, service_name: str) -> List[Dict[str, Any]]:
        """
        Fetches granular resource usage metrics from CloudWatch.
        Note: Current implementation relies on Cost Explorer for aggregate analysis.
        """
        logger.debug("resource_usage_interface_not_active", service=service_name)
        return []
