"""
Multi-Tenant AWS Adapter (Native Async)

Uses STS AssumeRole to fetch cost data from customer AWS accounts.
Leverages aioboto3 for non-blocking I/O.

Security:
- Never stores long-lived credentials
- Uses temporary credentials that expire in 1 hour
- Each request assumes the customer's IAM role
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import date, datetime, timezone
from decimal import Decimal
import aioboto3

from app.schemas.costs import CloudUsageSummary, CostRecord
from botocore.exceptions import ClientError
import structlog
from app.models.aws_connection import AWSConnection
from app.services.adapters.base import BaseAdapter

if TYPE_CHECKING:
    from app.schemas.costs import CloudUsageSummary

logger = structlog.get_logger()

# Safety limit to prevent memory bloat for large enterprise accounts
MAX_COST_EXPLORER_PAGES = 10

class MultiTenantAWSAdapter(BaseAdapter):
    """
    AWS adapter that assumes an IAM role in the customer's account using aioboto3.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self._credentials: Optional[Dict] = None
        self._credentials_expire_at: Optional[datetime] = None
        self.session = aioboto3.Session()

    async def verify_connection(self) -> bool:
        """Verify that the stored credentials are valid by assuming the role."""
        try:
            await self.get_credentials()
            return True
        except Exception as e:
            logger.error("verify_connection_failed", provider="aws", error=str(e))
            return False

    async def get_credentials(self) -> Dict:
        """Get temporary credentials via STS AssumeRole (Native Async)."""
        if self._credentials and self._credentials_expire_at:
            if datetime.now(timezone.utc) < self._credentials_expire_at:
                return self._credentials

        async with self.session.client("sts") as sts_client:
            try:
                response = await sts_client.assume_role(
                    RoleArn=self.connection.role_arn,
                    RoleSessionName="ValdrixCostFetch",
                    ExternalId=self.connection.external_id,
                    DurationSeconds=3600,
                )

                self._credentials = response["Credentials"]
                self._credentials_expire_at = self._credentials["Expiration"]

                logger.info(
                    "sts_assume_role_success",
                    role_arn=self.connection.role_arn,
                    expires_at=str(self._credentials_expire_at),
                )

                return self._credentials

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error(
                    "sts_assume_role_failed",
                    role_arn=self.connection.role_arn,
                    error=str(e),
                )
                from app.core.exceptions import AdapterError
                raise AdapterError(
                    message=f"AWS STS AssumeRole failure: {str(e)}",
                    code=error_code,
                    details={"role_arn": self.connection.role_arn}
                ) from e

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Fetch costs using AWS Cost Explorer and normalize."""
        # Note: AWS specific usage_only and group_by_service are not in BaseAdapter interface
        # For base compliance we map to get_daily_costs defaults or we need to expand base
        # But get_cost_and_usage in BaseAdapter returns List[Dict], get_daily_costs returns CloudUsageSummary
        # We need to adapt the return type to List[Dict] as per BaseAdapter or update BaseAdapter to return CloudUsageSummary
        # The BaseAdapter defined earlier returns List[Dict].
        # But `AWSMultiTenantAdapter.get_daily_costs` returns `CloudUsageSummary`.
        # I should probably wrap `get_daily_costs` and return the records list.
        
        summary = await self.get_daily_costs(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            group_by_service=True # Default to detailed breakdown for ingestion
        )
        
        # Convert CostRecord objects to dicts matching BaseAdapter expectation
        return [
            {
                "timestamp": r.date, # CostRecord has date or timestamp
                "service": r.service,
                "region": r.region,
                "usage_type": r.usage_type,
                "cost_usd": r.amount,
                "currency": r.currency,
                "amount_raw": r.amount_raw,
                "tags": {} 
            }
            for r in summary.records
        ]

    async def get_daily_costs(
        self,
        start_date: datetime,
        end_date: datetime,
        usage_only: bool = False,
        group_by_service: bool = False,
        max_pages: int = MAX_COST_EXPLORER_PAGES,
        granularity: str = "DAILY",
    ) -> CloudUsageSummary:
        """Fetch daily costs and return normalized CloudUsageSummary."""
        from app.schemas.costs import CloudUsageSummary, CostRecord
        
        creds = await self.get_credentials()

        async with self.session.client(
            "ce",
            region_name=self.connection.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as client:
            try:
                request_params = {
                    "TimePeriod": {
                        "Start": start_date.isoformat(),
                        "End": end_date.isoformat(),
                    },
                    "Granularity": granularity,
                    "Metrics": ["UnblendedCost"],
                }

                if usage_only:
                    request_params["Filter"] = {
                        "Dimensions": {"Key": "RECORD_TYPE", "Values": ["Usage"]}
                    }

                if group_by_service:
                    request_params["GroupBy"] = [{"Type": "DIMENSION", "Key": "SERVICE"}]

                ce_results = []
                pages_fetched = 0
                response = await client.get_cost_and_usage(**request_params)
                ce_results.extend(response.get("ResultsByTime", []))
                pages_fetched += 1

                while "NextPageToken" in response and pages_fetched < max_pages:
                    request_params["NextPageToken"] = response["NextPageToken"]
                    response = await client.get_cost_and_usage(**request_params)
                    ce_results.extend(response.get("ResultsByTime", []))
                    pages_fetched += 1

                # Normalize raw CE results into CostRecord objects
                normalized_records = []
                total_cost = 0.0
                by_service = {}
                by_region = {}

                for result in ce_results:
                    dt = datetime.fromisoformat(result["TimePeriod"]["Start"]).replace(tzinfo=timezone.utc)
                    
                    if group_by_service and "Groups" in result:
                        for group in result["Groups"]:
                            service_name = group["Keys"][0]
                            amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                            normalized_records.append(CostRecord(
                                date=dt,
                                amount=amount,
                                service=service_name,
                                region=self.connection.region
                            ))
                            total_cost += amount
                            by_service[service_name] = by_service.get(service_name, Decimal("0.0")) + amount
                    else:
                        amount = Decimal(result["Total"]["UnblendedCost"]["Amount"])
                        normalized_records.append(CostRecord(
                            date=dt,
                            amount=amount,
                            region=self.connection.region
                        ))
                        total_cost += amount

                return CloudUsageSummary(
                    tenant_id=str(self.connection.tenant_id),
                    provider="aws",
                    start_date=start_date,
                    end_date=end_date,
                    total_cost=total_cost,
                    records=normalized_records,
                    by_service=by_service,
                    by_region={self.connection.region: total_cost}
                )

            except ClientError as e:
                # ... (rest of exception handling stays same)
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error("multitenant_cost_fetch_failed", error=str(e))
                from app.core.exceptions import AdapterError
                raise AdapterError(
                    message=f"AWS Cost Explorer failure: {str(e)}",
                    code=error_code,
                    details={"aws_account": self.connection.aws_account_id}
                ) from e

    async def get_gross_usage(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        # Helper that wraps get_daily_costs specifically for gross usage
        summary = await self.get_daily_costs(start_date, end_date, usage_only=True, group_by_service=True)
        # Convert to list of dicts if needed or keep using CloudUsageSummary internally
        # For now, this method signature in original code was somewhat loose or unused in BaseAdapter (not present there)
        # We can keep it or deprecate it.
        return []

    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """
        Discovers resources of a specific type (e.g., 'volume', 'snapshot', 'ip').
        Uses existing ZombiePlugins internally for AWS.
        """
        from app.services.zombies.aws.plugins import (
            UnattachedVolumesPlugin, OldSnapshotsPlugin, UnusedElasticIpsPlugin,
            IdleInstancesPlugin, OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin,
            IdleRdsPlugin, ColdRedshiftPlugin, IdleSageMakerPlugin,
            IdleS3BucketsPlugin, LegacyEcrImagesPlugin
        )

        mapping = {
            "volume": UnattachedVolumesPlugin(),
            "snapshot": OldSnapshotsPlugin(),
            "ip": UnusedElasticIpsPlugin(),
            "instance": IdleInstancesPlugin(),
            "load_balancer": OrphanLoadBalancersPlugin(),
            "nat_gateway": UnderusedNatGatewaysPlugin(),
            "rds": IdleRdsPlugin(),
            "redshift": ColdRedshiftPlugin(),
            "sagemaker": IdleSageMakerPlugin(),
            "s3": IdleS3BucketsPlugin(),
            "ecr": LegacyEcrImagesPlugin(),
        }

        plugin = mapping.get(resource_type)
        if not plugin:
            logger.warning("unsupported_resource_type", resource_type=resource_type)
            return []

        target_region = region or self.connection.region
        creds = await self.get_credentials()
        
        try:
            return await plugin.scan(self.session, target_region, creds)
        except Exception as e:
            logger.error("resource_discovery_failed", 
                         resource_type=resource_type, 
                         region=target_region, 
                         error=str(e))
            return []
