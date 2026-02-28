"""
Multi-Tenant AWS Adapter (Native Async)

Uses STS AssumeRole to fetch cost data from customer AWS accounts.
Leverages aioboto3 for non-blocking I/O.

"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING, AsyncGenerator
from datetime import datetime, timezone
import aioboto3
from botocore.config import Config as BotoConfig

import structlog
from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.resource_usage_projection import (
    project_cost_rows_to_resource_usage,
)
from app.shared.core.config import get_settings
from app.shared.core.credentials import AWSCredentials
import tenacity
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    ReadTimeoutError,
    EndpointConnectionError,
)
from app.shared.core.exceptions import AdapterError, ConfigurationError

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

_RESOURCE_USAGE_SERVICE_ALIASES: Dict[str, str] = {
    "ec2": "instance",
    "instance": "instance",
    "instances": "instance",
    "ebs": "volume",
    "volume": "volume",
    "volumes": "volume",
    "eip": "eip",
    "elasticip": "eip",
    "nat": "nat_gateway",
    "nat_gateway": "nat_gateway",
    "rds": "rds",
    "redshift": "redshift",
    "s3": "s3",
    "ecr": "ecr",
    "sagemaker": "sagemaker",
}

# Standardized boto config with timeouts to prevent indefinite hangs
# SEC-03: Socket timeouts for all AWS API calls
BOTO_CONFIG = BotoConfig(
    read_timeout=30, connect_timeout=10, retries={"max_attempts": 3, "mode": "adaptive"}
)

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
        "retry": tenacity.retry_if_exception_type(
            (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)
        ),
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

    def __init__(self, credentials: AWSCredentials):
        self.credentials = credentials
        self.last_error: Optional[str] = None
        self._temp_credentials: Optional[dict[str, Any]] = None
        self._temp_credentials_expire_at: Optional[datetime] = None
        self.session = aioboto3.Session()

    @with_aws_retry
    async def verify_connection(self) -> bool:
        """Verify that the stored credentials are valid by assuming the role."""
        self._clear_last_error()
        try:
            # BE-ADAPT-1: Regional white-listing
            settings = get_settings()
            if self.credentials.region not in settings.AWS_SUPPORTED_REGIONS:
                self._set_last_error(
                    f"Unsupported AWS region '{self.credentials.region}' for role verification"
                )
                logger.error(
                    "invalid_aws_region_rejected",
                    region=self.credentials.region,
                    account_id=self.credentials.account_id,
                )
                return False

            await self.get_credentials()
            return True
        except Exception as e:
            self._set_last_error_from_exception(
                e, prefix="AWS STS role verification failed"
            )
            logger.error("verify_connection_failed", provider="aws", error=str(e))
            return False

    @with_aws_retry
    async def get_credentials(self) -> dict[str, Any]:
        """Get temporary credentials via STS AssumeRole (Native Async)."""
        if self._temp_credentials and self._temp_credentials_expire_at:
            if datetime.now(timezone.utc) < self._temp_credentials_expire_at:
                return self._temp_credentials

        STS_CONFIG = BotoConfig(
            read_timeout=10, connect_timeout=5, retries={"max_attempts": 2}
        )
        async with self.session.client("sts", config=STS_CONFIG) as sts_client:
            try:
                response = await sts_client.assume_role(
                    RoleArn=self.credentials.role_arn,
                    RoleSessionName="ValdrixCostFetch",
                    ExternalId=self.credentials.external_id,
                    DurationSeconds=3600,
                )

                self._temp_credentials = response["Credentials"]
                self._temp_credentials_expire_at = self._temp_credentials["Expiration"]

                logger.info(
                    "sts_role_assumed",
                    account_id=self.credentials.account_id,
                    expires_at=str(self._temp_credentials_expire_at),
                )

                return self._temp_credentials

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
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """
        MultiTenantAWSAdapter does not support Cost Explorer cost ingestion.
        Users must configure CUR for cost ingestion.
        """
        raise ConfigurationError(
            "Cost ingestion requires CUR (Cost and Usage Report) configuration. "
            "MultiTenantAWSAdapter is now restricted to resource discovery. "
            "Please configure S3-based CUR to enable cost analysis."
        )

    async def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        MultiTenantAWSAdapter no longer supports direct cost fetching.
        """
        # Yield nothing or raise error? consistent with get_cost_and_usage
        raise ConfigurationError(
            "Cost ingestion requires CUR configuration. "
            "Please configure S3-based CUR to enable cost analysis."
        )
        yield {}  # unreachable, but satisfies AsyncGenerator return type hint

    @with_aws_retry
    async def discover_resources(
        self, resource_type: str, region: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Discover zombie resources with OTel tracing.
        """
        # BE-ADAPT-1: Regional white-listing
        settings = get_settings()
        target_region = region or self.credentials.region
        if target_region not in settings.AWS_SUPPORTED_REGIONS:
            logger.error(
                "unsupported_aws_region_skip_scan",
                region=target_region,
                tenant_id=str(self.credentials.tenant_id),
            )
            return []

        from app.shared.core.tracing import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("aws_discover_resources") as span:
            span.set_attribute("tenant_id", str(self.credentials.tenant_id))
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
                logger.warning(
                    "plugin_not_found_for_resource", resource_type=resource_type
                )
                return []

            target_region = region or self.credentials.region
            creds = await self.get_credentials()

            try:
                return await target_plugin.scan(
                    self.session, target_region, creds, config=BOTO_CONFIG
                )
            except Exception as e:
                logger.error(
                    "resource_discovery_failed",
                    resource_type=resource_type,
                    region=target_region,
                    error=str(e),
                )
                return []

    async def get_resource_usage(
        self, service_name: str, resource_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        target_service = service_name.strip()
        if not target_service:
            return []

        resource_type = _RESOURCE_USAGE_SERVICE_ALIASES.get(
            target_service.lower(), target_service
        )
        resources = await self.discover_resources(resource_type)
        if not resources:
            return []

        now = datetime.now(timezone.utc)
        seed_rows: List[Dict[str, Any]] = []
        for item in resources:
            if not isinstance(item, dict):
                continue
            seed_rows.append(
                {
                    "provider": "aws",
                    "service": target_service,
                    "resource_id": item.get("resource_id") or item.get("id"),
                    "usage_type": "inventory",
                    "usage_amount": 1.0,
                    "usage_unit": "resource",
                    "cost_usd": 0.0,
                    "amount_raw": 0.0,
                    "currency": "USD",
                    "region": item.get("region") or item.get("location") or "global",
                    "timestamp": now,
                    "source_adapter": "aws_resource_discovery",
                    "tags": item.get("tags") if isinstance(item.get("tags"), dict) else {},
                }
            )

        return project_cost_rows_to_resource_usage(
            cost_rows=seed_rows,
            service_name=target_service,
            resource_id=resource_id,
            default_provider="aws",
            default_source_adapter="aws_resource_discovery",
        )
