from __future__ import annotations

from typing import Optional

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import BaseRemediationAction, RemediationContext
from app.modules.optimization.domain.actions.base import (
    ExecutionResult,
    ExecutionStatus,
)
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.shared.core.pricing import FeatureFlag


class BaseSaaSAction(BaseRemediationAction):
    """
    Base class for SaaS remediation actions.
    Provides httpx client with SaaS credentials.
    """

    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.CLOUD_PLUS_CONNECTORS

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return bool(resource_id and str(resource_id).strip())

    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        # SaaS backups (e.g., exporting user data before deletion) could be implemented here
        return None


@RemediationActionFactory.register("saas", RemediationAction.MANUAL_REVIEW)
class SaaSManualReviewAction(BaseSaaSAction):
    async def _perform_action(
        self, resource_id: str, context: RemediationContext
    ) -> ExecutionResult:
        raw_credentials = context.credentials or {}
        vendor = (
            str(raw_credentials.get("vendor") or "saas")
            if isinstance(raw_credentials, dict)
            else "saas"
        )
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.MANUAL_REVIEW.value,
            metadata={
                "provider": "saas",
                "vendor": vendor,
                "manual_follow_up_required": True,
            },
        )
