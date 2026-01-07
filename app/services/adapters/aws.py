from typing import List, Dict, Any
from datetime import date
import boto3
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
        # 'ce' = Cost Explorer
        self.client = boto3.client(
            "ce", 
            region_name=self.settings.AWS_DEFAULT_REGION,
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY
        )

    async def get_daily_costs(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Fetches daily cost/usage from AWS Cost Explorer.
        """
        try:
            # AWS requires strings in 'YYYY-MM-DD' format
            response = self.client.get_cost_and_usage(
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
            logger.error("aws_cost_fetch_failed", error=str(e))
            return []
            

        
    async def get_resource_usage(self, service_name: str) -> List[Dict[str, Any]]:
        # Placeholder for CloudWatch metrics
        return []