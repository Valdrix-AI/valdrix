from typing import Optional
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import BaseRemediationAction, ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.shared.core.pricing import FeatureFlag
from app.shared.adapters.license import LicenseAdapter
from app.shared.core.credentials import LicenseCredentials
import structlog

logger = structlog.get_logger()
class BaseLicenseAction(BaseRemediationAction):
    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.CLOUD_PLUS_CONNECTORS

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return bool(resource_id and str(resource_id).strip())

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        return None


@RemediationActionFactory.register("license", RemediationAction.RECLAIM_LICENSE_SEAT)
class LicenseReclaimSeatAction(BaseLicenseAction):
    @staticmethod
    def _build_credentials(raw_credentials: object) -> LicenseCredentials:
        if isinstance(raw_credentials, LicenseCredentials):
            return raw_credentials
        if isinstance(raw_credentials, dict):
            connector_config = raw_credentials.get("connector_config")
            license_feed = raw_credentials.get("license_feed")
            return LicenseCredentials(
                vendor=str(raw_credentials.get("vendor") or "unknown"),
                auth_method=str(raw_credentials.get("auth_method") or "manual"),
                api_key=raw_credentials.get("api_key"),
                connector_config=(
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                license_feed=license_feed if isinstance(license_feed, list) else [],
            )
        raise ValueError("Invalid license credentials payload")

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        """
        Native license reclamation using LicenseAdapter.
        Triggered for vendors like Google Workspace.
        """
        credentials: LicenseCredentials | None = None
        try:
            credentials = self._build_credentials(context.credentials or {})
            adapter = LicenseAdapter(credentials)
            
            # Extract SKU from parameters if provided (e.g. from analyzer metadata)
            params = context.parameters or {}
            sku_id = params.get("sku_id")
            
            success = await adapter.revoke_license(resource_id, sku_id=sku_id)
            
            if success:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    resource_id=resource_id,
                    action_taken=RemediationAction.RECLAIM_LICENSE_SEAT.value,
                    metadata={"provider": adapter._vendor, "sku_id": sku_id}
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    resource_id=resource_id,
                    action_taken=RemediationAction.RECLAIM_LICENSE_SEAT.value,
                    error_message="License revocation failed or user not found with specified SKUs."
                )
        except NotImplementedError as e:
            vendor_name = (
                credentials.vendor
                if credentials is not None
                else str((context.credentials or {}).get("vendor", "unknown"))
                if isinstance(context.credentials, dict)
                else "unknown"
            )
            logger.info("license_reclamation_manual_fallback", vendor=vendor_name)
            return ExecutionResult(
                status=ExecutionStatus.SKIPPED,
                resource_id=resource_id,
                action_taken=RemediationAction.RECLAIM_LICENSE_SEAT.value,
                error_message=f"Manual follow-up required: {str(e)}",
                metadata={"reason": "manual_follow_up_required"},
            )
        except Exception as e:
            logger.error("license_reclamation_failed", error=str(e))
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id=resource_id,
                action_taken=RemediationAction.RECLAIM_LICENSE_SEAT.value,
                error_message=str(e)
            )
