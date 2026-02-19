from typing import Optional
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import BaseRemediationAction, ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.shared.core.pricing import FeatureFlag


class BaseLicenseAction(BaseRemediationAction):
    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.CLOUD_PLUS_CONNECTORS

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        return None


@RemediationActionFactory.register("license", RemediationAction.RECLAIM_LICENSE_SEAT)
class LicenseReclaimSeatAction(BaseLicenseAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        """
        Native license reclamation using LicenseAdapter.
        Triggered for vendors like Google Workspace.
        """
        try:
            adapter = LicenseAdapter(context.credentials)
            
            # Extract SKU from parameters if provided (e.g. from analyzer metadata)
            sku_id = context.parameters.get("sku_id")
            
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
                    error_message="License revocation failed or user not found with specified SKUs."
                )
        except NotImplementedError as e:
            # Fallback for vendors without native API support
            logger.info("license_reclamation_manual_fallback", vendor=str(getattr(context.credentials, 'vendor', 'unknown')))
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.RECLAIM_LICENSE_SEAT.value,
                metadata={"info": f"Manual follow-up required: {str(e)}"}
            )
        except Exception as e:
            logger.error("license_reclamation_failed", error=str(e))
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id=resource_id,
                error_message=str(e)
            )
