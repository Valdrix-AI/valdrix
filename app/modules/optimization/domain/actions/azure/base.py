from typing import Any, Optional

from app.modules.optimization.adapters.common.remediation_clients import (
    create_azure_action_credential,
    create_azure_compute_client,
)
from app.modules.optimization.domain.actions.base import BaseRemediationAction, RemediationContext
from app.shared.core.pricing import FeatureFlag


class BaseAzureAction(BaseRemediationAction):
    """
    Base class for Azure remediation actions.
    Provides ComputeManagementClient management.
    """

    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.MULTI_CLOUD

    def __init__(self) -> None:
        self._credential: Optional[Any] = None
        self._compute_client: Optional[Any] = None

    async def _get_credentials(self, context: RemediationContext) -> Any:
        if not self._credential:
            self._credential = create_azure_action_credential(context.credentials or {})
        return self._credential

    async def _get_compute_client(self, context: RemediationContext) -> Any:
        if not self._compute_client:
            creds = await self._get_credentials(context)
            subscription_id = str((context.credentials or {}).get("subscription_id", ""))
            self._compute_client = create_azure_compute_client(
                credential=creds, subscription_id=subscription_id
            )
        return self._compute_client

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # Backup (Snapshot) for Azure VM disks could be implemented here
        return None
