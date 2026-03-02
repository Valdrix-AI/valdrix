from typing import Optional
from azure.identity.aio import ClientSecretCredential
from azure.mgmt.compute.aio import ComputeManagementClient
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
        self._credential: Optional[ClientSecretCredential] = None
        self._compute_client: Optional[ComputeManagementClient] = None

    async def _get_credentials(self, context: RemediationContext) -> ClientSecretCredential:
        if not self._credential:
            creds = context.credentials or {}
            # Valdrics typically stores these in SecretStr or sensitive dicts
            # Assuming context.credentials contains client_id, tenant_id, client_secret
            tenant_id = str(creds.get("tenant_id", ""))
            client_id = str(creds.get("client_id", ""))
            client_secret = str(creds.get("client_secret", ""))
            self._credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        return self._credential

    async def _get_compute_client(self, context: RemediationContext) -> ComputeManagementClient:
        if not self._compute_client:
            creds = await self._get_credentials(context)
            subscription_id = str((context.credentials or {}).get("subscription_id", ""))
            self._compute_client = ComputeManagementClient(
                credential=creds, subscription_id=subscription_id
            )
        return self._compute_client

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return True

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # Backup (Snapshot) for Azure VM disks could be implemented here
        return None
