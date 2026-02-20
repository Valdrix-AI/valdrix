from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("aws", RemediationAction.STOP_INSTANCE)
class AWSStopInstanceAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            await ec2.stop_instances(InstanceIds=[resource_id])
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.STOP_INSTANCE.value
            )


@RemediationActionFactory.register("aws", RemediationAction.TERMINATE_INSTANCE)
class AWSTerminateInstanceAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            await ec2.terminate_instances(InstanceIds=[resource_id])
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.TERMINATE_INSTANCE.value
            )


@RemediationActionFactory.register("aws", RemediationAction.RESIZE_INSTANCE)
class AWSResizeInstanceAction(BaseAWSAction):
    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        if not context.parameters or "target_instance_type" not in context.parameters:
            return False
        return True

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        if not context.parameters:
            raise ValueError("context.parameters missing")
        target_type = context.parameters["target_instance_type"]
        async with await self._get_client("ec2", context) as ec2:
            # AWS Resize requires instance to be stopped
            await ec2.stop_instances(InstanceIds=[resource_id])
            
            # Wait for instance to stop (simple poll)
            waiter = ec2.get_waiter('instance_stopped')
            await waiter.wait(InstanceIds=[resource_id])
            
            # Modify attribute
            await ec2.modify_instance_attribute(
                InstanceId=resource_id,
                InstanceType={'Value': target_type}
            )
            
            # Start instance back up
            await ec2.start_instances(InstanceIds=[resource_id])
            
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.RESIZE_INSTANCE.value,
                metadata={"target_type": target_type}
            )
@RemediationActionFactory.register("aws", RemediationAction.DELETE_SNAPSHOT)
class AWSDeleteSnapshotAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            await ec2.delete_snapshot(SnapshotId=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_SNAPSHOT.value
            )


@RemediationActionFactory.register("aws", RemediationAction.RELEASE_ELASTIC_IP)
class AWSReleaseElasticIpAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            await ec2.release_address(AllocationId=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.RELEASE_ELASTIC_IP.value
            )


@RemediationActionFactory.register("aws", RemediationAction.DELETE_NAT_GATEWAY)
class AWSDeleteNatGatewayAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            await ec2.delete_nat_gateway(NatGatewayId=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_NAT_GATEWAY.value
            )
