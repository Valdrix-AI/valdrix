from __future__ import annotations

from typing import Optional

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import (
    BaseRemediationAction,
    ExecutionResult,
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.shared.core.credentials import HybridCredentials
from app.shared.core.pricing import FeatureFlag


class BaseHybridAction(BaseRemediationAction):
    @property
    def required_feature(self) -> FeatureFlag:
        return FeatureFlag.CLOUD_PLUS_CONNECTORS

    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        return bool(resource_id and str(resource_id).strip())

    async def create_backup(
        self, resource_id: str, context: RemediationContext
    ) -> Optional[str]:
        return None


@RemediationActionFactory.register("hybrid", RemediationAction.MANUAL_REVIEW)
class HybridManualReviewAction(BaseHybridAction):
    @staticmethod
    def _build_credentials(raw_credentials: object) -> HybridCredentials:
        if isinstance(raw_credentials, HybridCredentials):
            return raw_credentials
        if isinstance(raw_credentials, dict):
            connector_config = raw_credentials.get("connector_config")
            spend_feed = raw_credentials.get("spend_feed")
            return HybridCredentials(
                vendor=str(raw_credentials.get("vendor") or "hybrid"),
                auth_method=str(raw_credentials.get("auth_method") or "manual"),
                api_key=raw_credentials.get("api_key"),
                api_secret=raw_credentials.get("api_secret"),
                connector_config=(
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                spend_feed=spend_feed if isinstance(spend_feed, list) else [],
            )
        raise ValueError("Invalid hybrid credentials payload")

    async def _perform_action(
        self, resource_id: str, context: RemediationContext
    ) -> ExecutionResult:
        creds = self._build_credentials(context.credentials or {})
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.MANUAL_REVIEW.value,
            metadata={
                "provider": "hybrid",
                "vendor": creds.vendor,
                "auth_method": creds.auth_method,
                "manual_follow_up_required": True,
            },
        )
