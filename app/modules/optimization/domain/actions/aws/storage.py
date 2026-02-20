from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("aws", RemediationAction.DELETE_S3_BUCKET)
class AWSDeleteS3BucketAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("s3", context) as s3:
            await s3.delete_bucket(Bucket=resource_id)
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_S3_BUCKET.value
            )


@RemediationActionFactory.register("aws", RemediationAction.DELETE_ECR_IMAGE)
class AWSDeleteEcrImageAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        # Expected resource_id format: repository@sha256:digest or repository:tag
        if "@" in resource_id:
            repo_name, image_digest = resource_id.split("@", 1)
            image_id = {"imageDigest": image_digest}
        else:
            repo_name, image_tag = resource_id.split(":", 1)
            image_id = {"imageTag": image_tag}

        async with await self._get_client("ecr", context) as ecr:
            await ecr.batch_delete_image(
                repositoryName=repo_name,
                imageIds=[image_id]
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_ECR_IMAGE.value
            )
