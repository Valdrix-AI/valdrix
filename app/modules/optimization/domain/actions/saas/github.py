import httpx
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.saas.base import BaseSaaSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("saas", RemediationAction.REVOKE_GITHUB_SEAT)
class GitHubRevokeSeatAction(BaseSaaSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        creds = context.credentials or {}
        token = creds.get("github_token")
        org = creds.get("organization")
        
        if not token or not org:
            raise ValueError("GitHub token or organization missing in credentials")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        async with httpx.AsyncClient() as client:
            # GitHub Remove organization member API
            url = f"https://api.github.com/orgs/{org}/members/{resource_id}"
            response = await client.delete(url, headers=headers)
            
            if response.status_code not in {204, 404}:
                raise Exception(f"GitHub API failed with status {response.status_code}: {response.text}")

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.REVOKE_GITHUB_SEAT.value
        )
