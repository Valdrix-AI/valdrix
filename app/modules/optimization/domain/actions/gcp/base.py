from typing import Any, Optional
from google.cloud import compute_v1
from google.oauth2 import service_account
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
        # GCP credentials are typically a service account JSON dict
        creds_info = context.credentials or {}
        if not creds_info:
            return None
        return service_account.Credentials.from_service_account_info(creds_info)  # type: ignore[no-untyped-call]

    async def _get_instances_client(self, context: RemediationContext) -> compute_v1.InstancesClient:
        creds = await self._get_credentials(context)
        return compute_v1.InstancesClient(credentials=creds)

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # GCP machine image or disk snapshot could be implemented here
        return None
