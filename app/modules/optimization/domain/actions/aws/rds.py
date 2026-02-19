from typing import Optional
import time
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


class BaseRDSSnapshotAction(BaseAWSAction):
    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        """Create a DB snapshot backup before deleting an RDS instance."""
        snapshot_id = f"valdrix-backup-{resource_id}-{int(time.time())}"
        async with await self._get_client("rds", context) as rds:
            await rds.create_db_snapshot(
                DBSnapshotIdentifier=snapshot_id,
                DBInstanceIdentifier=resource_id,
                Tags=[
                    {"Key": "Valdrix", "Value": "remediation-backup"},
                ],
            )
            return snapshot_id


@RemediationActionFactory.register("aws", RemediationAction.STOP_RDS_INSTANCE)
class AWSStopRdsInstanceAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("rds", context) as rds:
            await rds.stop_db_instance(DBInstanceIdentifier=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.STOP_RDS_INSTANCE.value
            )


@RemediationActionFactory.register("aws", RemediationAction.DELETE_RDS_INSTANCE)
class AWSDeleteRdsInstanceAction(BaseRDSSnapshotAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("rds", context) as rds:
            await rds.delete_db_instance(
                DBInstanceIdentifier=resource_id,
                SkipFinalSnapshot=True
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_RDS_INSTANCE.value
            )
