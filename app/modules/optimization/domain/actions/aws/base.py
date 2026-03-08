from typing import Any, Optional

from app.modules.optimization.adapters.common.remediation_clients import (
    build_aws_client,
    create_aws_session,
)
from app.modules.optimization.domain.actions.base import BaseRemediationAction, RemediationContext
from app.shared.core.config import get_settings


class BaseAWSAction(BaseRemediationAction):
    """
    Base class for AWS remediation actions.
    Provides aioboto3 client management.
    """

    def __init__(self) -> None:
        self.session = create_aws_session()

    async def _get_client(self, service_name: str, context: RemediationContext) -> Any:
        """Helper to get aioboto3 client with context credentials."""
        settings = get_settings()
        return build_aws_client(
            session=self.session,
            service_name=service_name,
            region=context.region,
            endpoint_url=settings.AWS_ENDPOINT_URL,
            raw_credentials=context.credentials,
        )

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        # Default validation is True, specific actions can override
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # Default no backup, specific actions (e.g., DeleteVolume) can override
        return None
