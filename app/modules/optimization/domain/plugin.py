from abc import ABC, abstractmethod
from typing import Any, Dict, List
import inspect
from app.shared.adapters.aws_utils import map_aws_credentials


# Estimated monthly costs (USD) used for zombie resource impact analysis
ESTIMATED_COSTS = {
    "ebs_volume_gb": 0.10,
    "elastic_ip": 3.60,
    "snapshot_gb": 0.05,
    "ec2_t3_micro": 7.50,
    "ec2_t3_small": 15.00,
    "ec2_t3_medium": 30.00,
    "ec2_m5_large": 69.12,
    "ec2_default": 10.00,
    "elb": 20.00,
    "s3_gb": 0.023,
    "ecr_gb": 0.10,
    "sagemaker_endpoint": 108.00,
    "redshift_cluster": 180.00,
    "nat_gateway": 32.40,
}


class _GuardedCloudWatchClient:
    """Proxy CloudWatch client calls through the cloud API budget governor."""

    _EXPENSIVE_OPS = {"get_metric_statistics", "get_metric_data"}

    def __init__(self, client: Any):
        self._client = client

    @staticmethod
    def _empty_payload_for(operation: str) -> dict[str, Any]:
        if operation == "get_metric_statistics":
            return {"Datapoints": []}
        if operation == "get_metric_data":
            return {"MetricDataResults": []}
        return {}

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if name not in self._EXPENSIVE_OPS or not callable(attr):
            return attr

        async def guarded_call(*args: Any, **kwargs: Any) -> Any:
            from app.modules.optimization.domain.cloud_api_budget import (
                allow_expensive_cloud_api_call,
            )

            allowed = await allow_expensive_cloud_api_call(
                "aws_cloudwatch",
                operation=name,
            )
            if not allowed:
                return self._empty_payload_for(name)

            result = attr(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        return guarded_call


class _GuardedCloudWatchContext:
    """Wrap aioboto3 client context manager to return a guarded CloudWatch client."""

    def __init__(self, context_manager: Any):
        self._context_manager = context_manager
        self._client = None

    async def __aenter__(self) -> _GuardedCloudWatchClient:
        self._client = await self._context_manager.__aenter__()
        return _GuardedCloudWatchClient(self._client)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        return await self._context_manager.__aexit__(exc_type, exc, tb)


class ZombiePlugin(ABC):
    """
    Abstract base class for Zombie Resource detection plugins.
    Each plugin is responsible for detecting a specific type of zombie resource.
    """

    @property
    @abstractmethod
    def category_key(self) -> str:
        """
        The dictionary key for results (e.g., 'unattached_volumes').
        Used to aggregate results in the final report.
        """
        raise NotImplementedError

    @abstractmethod
    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Scan for zombie resources.

        Subclasses should document their expected arguments (e.g., session, client, region).
        """
        raise NotImplementedError

    def _get_client(
        self,
        session: Any,
        service_name: str,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
    ) -> Any:
        """Helper to get AWS client with optional credentials and config."""
        from app.shared.core.config import get_settings

        settings = get_settings()

        kwargs = {"region_name": region}
        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL

        if credentials:
            kwargs.update(map_aws_credentials(credentials))

        if config:
            kwargs["config"] = config
        client_context = session.client(service_name, **kwargs)
        if service_name == "cloudwatch":
            return _GuardedCloudWatchContext(client_context)
        return client_context
