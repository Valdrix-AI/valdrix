import httpx
from app.shared.core.credentials import SaaSCredentials
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.saas.base import BaseSaaSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
import structlog

logger = structlog.get_logger()


@RemediationActionFactory.register("saas", RemediationAction.REVOKE_GITHUB_SEAT)
class GitHubRevokeSeatAction(BaseSaaSAction):
    @staticmethod
    def _build_credentials(raw_credentials: object) -> SaaSCredentials:
        if isinstance(raw_credentials, SaaSCredentials):
            return raw_credentials
        if isinstance(raw_credentials, dict):
            connector_config = raw_credentials.get("connector_config")
            spend_feed = raw_credentials.get("spend_feed")
            return SaaSCredentials(
                platform=str(raw_credentials.get("vendor") or "github"),
                api_key=raw_credentials.get("api_key"),
                auth_method=str(raw_credentials.get("auth_method") or "manual"),
                connector_config=(
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                spend_feed=spend_feed if isinstance(spend_feed, list) else [],
            )
        raise ValueError("Invalid SaaS credentials payload")

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        credentials = self._build_credentials(context.credentials or {})
        connector_config = credentials.connector_config
        raw_token = credentials.api_key
        token = ""
        if raw_token is not None:
            token = (
                raw_token.get_secret_value()
                if hasattr(raw_token, "get_secret_value")
                else str(raw_token).strip()
            )
        org = str(
            connector_config.get("github_org")
            or connector_config.get("organization")
            or ""
        ).strip()

        if not token or not org:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id=resource_id,
                action_taken=RemediationAction.REVOKE_GITHUB_SEAT.value,
                error_message=(
                    "GitHub revoke requires api_key and connector_config.github_org"
                ),
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # GitHub Remove organization member API
                url = f"https://api.github.com/orgs/{org}/members/{resource_id}"
                response = await client.delete(url, headers=headers)

                if response.status_code not in {204, 404}:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        resource_id=resource_id,
                        action_taken=RemediationAction.REVOKE_GITHUB_SEAT.value,
                        error_message=(
                            f"GitHub API failed with status {response.status_code}: "
                            f"{response.text[:200]}"
                        ),
                    )
        except httpx.HTTPError as exc:
            logger.warning("github_revoke_http_failed", error=str(exc), org=org)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id=resource_id,
                action_taken=RemediationAction.REVOKE_GITHUB_SEAT.value,
                error_message=f"GitHub API request failed: {exc}",
            )

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.REVOKE_GITHUB_SEAT.value,
            metadata={"provider": "github", "organization": org},
        )
