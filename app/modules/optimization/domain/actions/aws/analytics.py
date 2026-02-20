from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("aws", RemediationAction.DELETE_REDSHIFT_CLUSTER)
class AWSDeleteRedshiftClusterAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("redshift", context) as redshift:
            await redshift.delete_cluster(
                ClusterIdentifier=resource_id,
                SkipFinalClusterSnapshot=True
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_REDSHIFT_CLUSTER.value
            )


@RemediationActionFactory.register("aws", RemediationAction.DELETE_SAGEMAKER_ENDPOINT)
class AWSDeleteSageMakerEndpointAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("sagemaker", context) as sagemaker:
            await sagemaker.delete_endpoint(EndpointName=resource_id)
            await sagemaker.delete_endpoint_config(EndpointConfigName=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_SAGEMAKER_ENDPOINT.value
            )
