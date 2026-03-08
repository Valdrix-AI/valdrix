from typing import Any, Optional

from app.modules.optimization.adapters.common.remediation_clients import (
    create_gcp_action_credentials,
    create_gcp_instances_client,
)
from app.modules.optimization.domain.actions.base import BaseRemediationAction, RemediationContext
from app.shared.core.pricing import FeatureFlag


class BaseGCPAction(BaseRemediationAction):
    """
    Base class for GCP remediation actions.
    Provides InstancesClient management.
    """

    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.MULTI_CLOUD

    async def _get_credentials(self, context: RemediationContext) -> Any:
        return create_gcp_action_credentials(context.credentials or None)

    async def _get_instances_client(self, context: RemediationContext) -> Any:
        return create_gcp_instances_client(context.credentials or None)

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # GCP machine image or disk snapshot could be implemented here
        return None
