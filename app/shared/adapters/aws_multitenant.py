"""
Multi-Tenant AWS Adapter (Native Async)

Uses STS AssumeRole to fetch cost data from customer AWS accounts.
Leverages aioboto3 for non-blocking I/O.

"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import date, datetime, timezone
from decimal import Decimal
import aioboto3
from botocore.config import Config as BotoConfig

from app.schemas.costs import CloudUsageSummary, CostRecord
import structlog
from app.models.aws_connection import AWSConnection
from app.shared.adapters.base import BaseAdapter
from app.shared.core.config import get_settings
import tenacity
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError
from app.shared.core.exceptions import AdapterError

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Standardized boto config with timeouts to prevent indefinite hangs
# SEC-03: Socket timeouts for all AWS API calls
BOTO_CONFIG = BotoConfig(
    read_timeout=30,
    connect_timeout=10,
    retries={"max_attempts": 3, "mode": "adaptive"}
)

# Safety limit to prevent infinite loops, set to a very high value (300 pages = ~10 years of daily data)
MAX_COST_EXPLORER_PAGES = 300

# BE-ADAPT-2: Global retry decorator for transient AWS connection issues
def with_aws_retry(func: Any) -> Any:
    """
    Exponential backoff retry decorator for AWS API calls.
    Targets transient network failures (ConnectTimeout, EndpointConnectionError).
    Supports both standard coroutines and async generators.
    """
    import inspect
    from functools import wraps

    def _before_sleep(retry_state: tenacity.RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        wait = retry_state.next_action.sleep if retry_state.next_action else None
        logger.debug(
            "aws_retrying",
            attempt=retry_state.attempt_number,
            wait_seconds=wait,
            error=str(exc) if exc else None,
            function=getattr(retry_state.fn, "__name__", "unknown"),
        )

    retry_config = {
        "retry": tenacity.retry_if_exception_type((ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)),
        "wait": tenacity.wait_exponential(multiplier=1, min=2, max=10),
        "stop": tenacity.stop_after_attempt(4),
        "before_sleep": _before_sleep,
        "reraise": True,
    }

    def _build_retry_config() -> Dict[str, Any]:
        config = dict(retry_config)
        settings = get_settings()
        if getattr(settings, "TESTING", False):
            # Avoid real sleeps during tests while preserving retry semantics.
            async def _no_sleep(_seconds: float) -> None:
                return None

            config["sleep"] = _no_sleep
            config["wait"] = tenacity.wait_none()
        return config

    if inspect.isasyncgenfunction(func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Async generators need manual retry orchestration.
            retrying = tenacity.AsyncRetrying(**_build_retry_config())
            async for attempt in retrying:
                with attempt:
                    async for item in func(*args, **kwargs):
                        yield item
        return wrapper
    else:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            retrying = tenacity.AsyncRetrying(**_build_retry_config())
            async for attempt in retrying:
                with attempt:
                    return await func(*args, **kwargs)
        return wrapper

class MultiTenantAWSAdapter(BaseAdapter):
    """
    AWS adapter that assumes an IAM role in the customer's account using aioboto3.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self._credentials: Optional[dict[str, Any]] = None
        self._credentials_expire_at: Optional[datetime] = None
        self.session = aioboto3.Session()

    @with_aws_retry
    async def verify_connection(self) -> bool:
        """Verify that the stored credentials are valid by assuming the role."""
        try:
            # BE-ADAPT-1: Regional white-listing
            settings = get_settings()
            if self.connection.region not in settings.AWS_SUPPORTED_REGIONS:
                logger.error("invalid_aws_region_rejected", 
                             region=self.connection.region,
                             tenant_id=str(self.connection.tenant_id))
                return False

            await self.get_credentials()
            return True
        except Exception as e:
            logger.error("verify_connection_failed", provider="aws", error=str(e))
            return False

    @with_aws_retry
    async def get_credentials(self) -> dict[str, Any]:
        """Get temporary credentials via STS AssumeRole (Native Async)."""
        if self._credentials and self._credentials_expire_at:
            if datetime.now(timezone.utc) < self._credentials_expire_at:
                return self._credentials

        STS_CONFIG = BotoConfig(
            read_timeout=10,
            connect_timeout=5,
            retries={"max_attempts": 2}
        )
        async with self.session.client("sts", config=STS_CONFIG) as sts_client:
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
                    expires_at=str(self._credentials_expire_at),
                )

                return self._credentials

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error(
                    "sts_assume_role_failed",
                    error=str(e),
                )
                raise AdapterError(
                    message=f"AWS STS AssumeRole failure: {str(e)}",
                    code=error_code,
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
        
        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date

        summary = await self.get_daily_costs(
            start_date=s_date,
            end_date=e_date,
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
        start_date: date,
        end_date: date,
        granularity: str = "DAILY",
        usage_only: bool = False,
        group_by_service: bool = True,
    ) -> CloudUsageSummary:
        """Fetch multi-region costs with OTel tracing."""
        from app.shared.core.tracing import get_tracer
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span("aws_fetch_costs") as span:
            span.set_attribute("tenant_id", str(self.connection.tenant_id))
            span.set_attribute("aws_account", self.connection.aws_account_id)
            
            # ... existing implementation ...
            # Convert date to datetime for stream method
            start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, datetime.min.time()).replace(tzinfo=timezone.utc)

            records = []
            total_cost = Decimal("0")

            async for record in self.stream_cost_and_usage(start_dt, end_dt, granularity):
                records.append(CostRecord(
                    date=record["timestamp"],
                    service=record["service"],
                    region=record["region"],
                    amount=record["cost_usd"],
                    currency=record["currency"],
                    amount_raw=record["amount_raw"],
                    usage_type=record["usage_type"]
                ))
                total_cost += record["cost_usd"]

            return CloudUsageSummary(
                tenant_id=str(self.connection.tenant_id),
                provider="aws",
                records=records,
                total_cost=total_cost,
                start_date=start_date,
                end_date=end_date
            )

    @with_aws_retry
    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        """
        Stream cost data from AWS Cost Explorer.
        Optimized to never hold the full dataset in memory.
        """
        creds = await self.get_credentials()

        async with self.session.client(
            "ce",
            region_name=self.connection.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            config=BOTO_CONFIG
        ) as client:
            try:
                request_params = {
                    "TimePeriod": {
                        "Start": start_date.strftime("%Y-%m-%d"),
                        "End": end_date.strftime("%Y-%m-%d"),
                    },
                    "Granularity": granularity,
                    "Metrics": ["AmortizedCost"],
                    "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
                }

                pages_fetched = 0
                while pages_fetched < MAX_COST_EXPLORER_PAGES:
                    response = await client.get_cost_and_usage(**request_params)
                    
                    results_by_time = response.get("ResultsByTime", [])
                    for result in results_by_time:
                        dt = datetime.fromisoformat(result["TimePeriod"]["Start"]).replace(tzinfo=timezone.utc)
                        if "Groups" in result:
                            for group in result["Groups"]:
                                service_name = group["Keys"][0]
                                amount = Decimal(group["Metrics"]["AmortizedCost"]["Amount"])
                                yield {
                                    "timestamp": dt,
                                    "service": service_name,
                                    "region": self.connection.region,
                                    "cost_usd": amount,
                                    "currency": "USD",
                                    "amount_raw": amount,
                                    "usage_type": "Usage",
                                    "source_adapter": "cost_explorer_api",
                                }
                    
                    pages_fetched += 1
                    if "NextPageToken" in response:
                        request_params["NextPageToken"] = response["NextPageToken"]
                    else:
                        break
                if pages_fetched >= MAX_COST_EXPLORER_PAGES and "NextPageToken" in response:
                    logger.warning(
                        "cost_explorer_page_limit_reached",
                        aws_account=self.connection.aws_account_id,
                        pages=pages_fetched
                    )
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error("multitenant_cost_fetch_failed", error=str(e))
                raise AdapterError(
                    message=f"AWS Cost Explorer failure: {str(e)}",
                    code=error_code,
                    details={"aws_account": self.connection.aws_account_id}
                ) from e

    async def get_gross_usage(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        # Helper that wraps get_daily_costs specifically for gross usage
        summary = await self.get_daily_costs(start_date, end_date, usage_only=True, group_by_service=True)
        return [
            {
                "date": r.date,
                "service": r.service,
                "region": r.region,
                "cost_usd": r.amount,
                "currency": r.currency,
                "usage_type": r.usage_type,
            }
            for r in summary.records
        ]

    async def get_amortized_costs(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """
        Fetch amortized costs (RI/Savings Plans spread across usage).
        Phase 2.3: RI & Savings Plan Amortization - AWS already uses AmortizedCost metric.
        This method provides API parity with Azure and GCP adapters.
        """
        return await self.get_cost_and_usage(start_date, end_date, granularity)

    @with_aws_retry
    async def discover_resources(self, resource_type: str, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Discover zombie resources with OTel tracing.
        """
        # BE-ADAPT-1: Regional white-listing
        settings = get_settings()
        target_region = region or self.connection.region
        if target_region not in settings.AWS_SUPPORTED_REGIONS:
            logger.error("unsupported_aws_region_skip_scan", 
                         region=target_region, 
                         tenant_id=str(self.connection.tenant_id))
            return []

        from app.shared.core.tracing import get_tracer
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span("aws_discover_resources") as span:
            span.set_attribute("tenant_id", str(self.connection.tenant_id))
            span.set_attribute("resource_type", resource_type)
            
            from app.modules.optimization.domain.registry import registry
            plugins = registry.get_plugins_for_provider("aws")
            
            # Simple heuristic to find the right plugin by resource_type
            mapping = {
                "volume": "storage",
                "snapshot": "storage",
                "ip": "compute",
                "instance": "compute",
                "nat_gateway": "network",
                "eip": "network",
                "load_balancer": "network",
                "db": "database",
                "rds": "database",
                "redshift": "database",
                "sagemaker": "analytics",
                "s3": "storage",
                "ecr": "containers",
            }
            
            target_plugin = None
            category = mapping.get(resource_type.lower())
            if category:
                for p in plugins:
                    if hasattr(p, "category") and p.category == category:
                        target_plugin = p
                        break
            
            if not target_plugin:
                logger.warning("plugin_not_found_for_resource", resource_type=resource_type)
                return []

            target_region = region or self.connection.region
            creds = await self.get_credentials()
            
            try:
                return await target_plugin.scan(self.session, target_region, creds, config=BOTO_CONFIG)
            except Exception as e:
                logger.error("resource_discovery_failed", 
                             resource_type=resource_type, 
                             region=target_region, 
                             error=str(e))
                return []
