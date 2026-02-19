from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID
from enum import Enum


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionResult:
    status: ExecutionStatus
    resource_id: str
    action_taken: str
    error_message: Optional[str] = None
    backup_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class RemediationContext:
    tenant_id: UUID
    region: str
    tier: str = "free"  # PricingTier.value
    credentials: Optional[Dict[str, str]] = None
    db_session: Any = None  # AsyncSession
    settings: Optional[Any] = None
    create_backup: bool = False
    backup_retention_days: int = 30
    parameters: Optional[Dict[str, Any]] = None


import structlog
from app.shared.core.retry import tenacity_retry
from app.shared.core.pricing import FeatureFlag, is_feature_enabled

logger = structlog.get_logger()

class BaseRemediationAction(ABC):
    """
    Abstract base class for all remediation actions.
    Implements the Strategy Pattern for multi-cloud/SaaS execution.
    """

    @abstractmethod
    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        """
        Pre-flight check to ensure the action can be safely executed.
        E.g., Check if a volume is actually detached before deletion.
        """
        pass

    @abstractmethod
    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        """
        Create a backup (snapshot/disk) before a destructive action.
        Returns the ID of the created backup.
        """
        pass

    @abstractmethod
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        """
        The actual implementation of the remediation action.
        """
        pass

    @property
    def required_feature(self) -> FeatureFlag:
        """
        The feature flag required to execute this action.
        Defaults to AUTO_REMEDIATION (Growth+).
        """
        return FeatureFlag.AUTO_REMEDIATION

    async def execute(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        """
        Perform the actual remediation action with retries and logging.
        """
        action_name = self.__class__.__name__
        logger.info("remediation_action_started", resource_id=resource_id, action=action_name)
        try:
            # 1. Tier/Feature Check
            if not is_feature_enabled(context.tier, self.required_feature):
                return ExecutionResult(
                    status=ExecutionStatus.SKIPPED,
                    resource_id=resource_id,
                    action_taken=action_name,
                    error_message=f"Feature '{self.required_feature.value}' not enabled for tier '{context.tier}'"
                )

            # 2. Validate
            if not await self.validate(resource_id, context):
                return ExecutionResult(
                    status=ExecutionStatus.SKIPPED,
                    resource_id=resource_id,
                    action_taken=action_name,
                    error_message="Validation failed"
                )

            # 2. Backup if requested
            backup_id = None
            if context.create_backup:
                 backup_id = await self.create_backup(resource_id, context)

            # 3. Perform with retry
            @tenacity_retry("external_api")
            async def wrapped_action():
                return await self._perform_action(resource_id, context)
            
            result = await wrapped_action()
            result.backup_id = backup_id
            
            logger.info("remediation_action_completed", resource_id=resource_id, action=action_name, status=result.status.value)
            return result
            
        except Exception as e:
            logger.error("remediation_action_failed", resource_id=resource_id, action=action_name, error=str(e))
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id=resource_id,
                action_taken=action_name,
                error_message=str(e)
            )
