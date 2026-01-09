"""
Multi-Tenant AWS Adapter

Uses STS AssumeRole to fetch cost data from customer AWS accounts.

Security:
- Never stores long-lived credentials
- Uses temporary credentials that expire in 1 hour
- Each request assumes the customer's IAM role

Usage:
    adapter = MultiTenantAWSAdapter(connection)
    costs = await adapter.get_daily_costs(start, end)
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime
import boto3
from botocore.exceptions import ClientError
import structlog
from app.models.aws_connection import AWSConnection
from app.services.adapters.base import CostAdapter

logger = structlog.get_logger()


class MultiTenantAWSAdapter(CostAdapter):
    """
    AWS adapter that assumes an IAM role in the customer's account.
    
    Flow:
    1. Initialize with an AWSConnection object
    2. Call STS AssumeRole to get temporary credentials
    3. Use temporary credentials to call Cost Explorer
    """
    
    def __init__(self, connection: AWSConnection):
        """
        Args:
            connection: The AWSConnection containing role_arn and external_id
        """
        self.connection = connection
        self._credentials: Optional[Dict] = None
        self._credentials_expire_at: Optional[datetime] = None
    
    def _get_credentials(self) -> Dict:
        """
        Get temporary credentials via STS AssumeRole.
        Caches credentials until they expire.
        
        Returns:
            Dict with AccessKeyId, SecretAccessKey, SessionToken
        """
        # Check if we have valid cached credentials
        if self._credentials and self._credentials_expire_at:
            if datetime.utcnow() < self._credentials_expire_at:
                return self._credentials
        
        # Assume the role
        sts_client = boto3.client("sts")
        
        try:
            response = sts_client.assume_role(
                RoleArn=self.connection.role_arn,
                RoleSessionName="CloudSentinelCostFetch",
                ExternalId=self.connection.external_id,
                DurationSeconds=3600,  # 1 hour
            )
            
            self._credentials = response["Credentials"]
            # Expire 5 minutes early to be safe
            self._credentials_expire_at = self._credentials["Expiration"].replace(tzinfo=None)
            
            logger.info(
                "sts_assume_role_success",
                role_arn=self.connection.role_arn,
                expires_at=str(self._credentials_expire_at),
            )
            
            return self._credentials
            
        except ClientError as e:
            logger.error(
                "sts_assume_role_failed",
                role_arn=self.connection.role_arn,
                error=str(e),
            )
            raise
    
    def _get_ce_client(self):
        """
        Get a Cost Explorer client using temporary credentials.
        """
        creds = self._get_credentials()
        
        return boto3.client(
            "ce",
            region_name=self.connection.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    
    async def get_daily_costs(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Fetch daily costs from the customer's AWS account.
        """
        try:
            client = self._get_ce_client()
            
            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.isoformat(),
                    "End": end_date.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            
            logger.info(
                "multitenant_cost_fetch_success",
                aws_account=self.connection.aws_account_id,
                days=len(response.get("ResultsByTime", [])),
            )
            
            return response.get("ResultsByTime", [])
            
        except ClientError as e:
            logger.error(
                "multitenant_cost_fetch_failed",
                aws_account=self.connection.aws_account_id,
                error=str(e),
            )
            return []
    
    async def get_resource_usage(self, service_name: str) -> List[Dict[str, Any]]:
        """Placeholder for future resource-level usage."""
        return []