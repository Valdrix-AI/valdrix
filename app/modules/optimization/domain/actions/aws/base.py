import aioboto3
from typing import Any, Optional
from app.modules.optimization.domain.actions.base import BaseRemediationAction, RemediationContext
from app.shared.adapters.aws_utils import map_aws_credentials
from app.shared.core.config import get_settings


class BaseAWSAction(BaseRemediationAction):
    """
    Base class for AWS remediation actions.
    Provides aioboto3 client management.
    """

    def __init__(self) -> None:
        self.session = aioboto3.Session()

    async def _get_client(self, service_name: str, context: RemediationContext) -> Any:
        """Helper to get aioboto3 client with context credentials."""
        settings = get_settings()
        kwargs = {"region_name": context.region}

        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL

        if context.credentials:
            kwargs.update(map_aws_credentials(context.credentials))

        return self.session.client(service_name, **kwargs)

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        # Default validation is True, specific actions can override
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # Default no backup, specific actions (e.g., DeleteVolume) can override
        return None
