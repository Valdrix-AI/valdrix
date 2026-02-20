from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("aws", RemediationAction.DELETE_LOAD_BALANCER)
class AWSDeleteLoadBalancerAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("elbv2", context) as elb:
            await elb.delete_load_balancer(LoadBalancerArn=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_LOAD_BALANCER.value
            )
