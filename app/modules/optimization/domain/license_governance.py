"""
License Governance Service - Autonomous SaaS/License Reclamation Loop.

Implements "Phase 8: Autonomous License Lifecycle" with a notify-before-revoke workflow.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Dict, Any, Tuple, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
import httpx
import structlog
from pydantic import SecretStr

from app.shared.core.service import BaseService
from app.models.license_connection import LicenseConnection
from app.models.remediation_settings import RemediationSettings
from app.models.remediation import RemediationAction, RemediationRequest, RemediationStatus
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.adapters.license import LicenseAdapter
from app.shared.core.credentials import LicenseCredentials
from app.shared.core.constants import SYSTEM_USER_ID
from app.shared.core.exceptions import ExternalAPIError
from app.shared.core.remediation_results import (
    normalize_remediation_status,
    parse_remediation_execution_error,
)

logger = structlog.get_logger()
_LIST_USERS_ACTIVITY_TIMEOUT_SECONDS = 30.0


class LicenseGovernanceService(BaseService):
    """
    Orchestrates autonomous license governance:
    1. Scan connections for inactive users.
    2. Create remediation requests (pending or scheduled).
    3. Generate optimization insights.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.remediation_service = RemediationService(db)

    async def get_governance_settings(self, tenant_id: UUID) -> RemediationSettings | None:
        result = await self.db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _normalize_user_id(raw_value: Any) -> Optional[str]:
        if raw_value is None:
            return None
        normalized = str(raw_value).strip()
        return normalized or None

    @staticmethod
    def _normalize_user_email(raw_value: Any) -> Optional[str]:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip().lower()
        if not normalized or "@" not in normalized:
            return None
        return normalized

    @staticmethod
    def _normalize_last_active(raw_value: Any) -> Tuple[Optional[datetime], bool]:
        """
        Normalize last-active timestamps.
        Returns (value, parse_error_flag).
        """
        if raw_value is None:
            return None, False

        if isinstance(raw_value, datetime):
            normalized = raw_value
            if normalized.tzinfo is None:
                normalized = normalized.replace(tzinfo=timezone.utc)
            return normalized, False

        if isinstance(raw_value, str):
            candidate = raw_value.strip()
            if not candidate:
                return None, True
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                return None, True
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed, False

        if isinstance(raw_value, (int, float)):
            try:
                return datetime.fromtimestamp(float(raw_value), tz=timezone.utc), False
            except (TypeError, ValueError, OverflowError):
                return None, True

        return None, True

    @staticmethod
    def _resolve_estimated_savings(connector_config: dict[str, Any]) -> float:
        raw = connector_config.get("default_seat_price_usd", 12.0)
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            return 12.0
        if amount <= 0:
            return 12.0
        return amount

    async def _has_pending_request(self, tenant_id: UUID, resource_id: str) -> bool:
        """Check for existing in-flight request for this user to avoid duplicates."""
        result = await self.db.execute(
            select(RemediationRequest.id).where(
                and_(
                    RemediationRequest.tenant_id == tenant_id,
                    RemediationRequest.resource_id == resource_id,
                    RemediationRequest.action == RemediationAction.RECLAIM_LICENSE_SEAT,
                    RemediationRequest.status.in_([
                        RemediationStatus.PENDING,
                        RemediationStatus.PENDING_APPROVAL,
                        RemediationStatus.APPROVED,
                        RemediationStatus.SCHEDULED,
                        RemediationStatus.EXECUTING,
                    ]),
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def run_tenant_governance(self, tenant_id: UUID) -> Dict[str, Any]:
        """
        Runs the governance loop for a specific tenant.
        """
        settings = await self.get_governance_settings(tenant_id)
        if not settings or not settings.license_auto_reclaim_enabled:
            logger.info("license_governance_skipped_disabled", tenant_id=str(tenant_id))
            return {"status": "skipped", "reason": "feature_disabled"}

        result = await self.db.execute(
            select(LicenseConnection).where(
                LicenseConnection.tenant_id == tenant_id,
                LicenseConnection.is_active.is_(True),
            )
        )
        connections = result.scalars().all()
        
        stats = {
            "connections_scanned": 0,
            "connections_timed_out": 0,
            "users_flagged": 0,
            "users_skipped_invalid": 0,
            "requests_created": 0,
            "duplicates_skipped": 0,
            "executions_completed": 0,
            "executions_failed": 0,
            "executions_deferred": 0,
        }
        
        for conn in connections:
            try:
                stats["connections_scanned"] += 1
                creds = LicenseCredentials(
                    vendor=conn.vendor,
                    auth_method=conn.auth_method,
                    api_key=SecretStr(conn.api_key) if conn.api_key else None,
                    connector_config=conn.connector_config
                    if isinstance(conn.connector_config, dict)
                    else {},
                    license_feed=conn.license_feed
                    if isinstance(conn.license_feed, list)
                    else [],
                )
                adapter = LicenseAdapter(creds)

                try:
                    users = await asyncio.wait_for(
                        adapter.list_users_activity(),
                        timeout=_LIST_USERS_ACTIVITY_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    stats["connections_timed_out"] += 1
                    logger.warning(
                        "license_governance_connection_timeout",
                        tenant_id=str(tenant_id),
                        connection_id=str(conn.id),
                        timeout_seconds=_LIST_USERS_ACTIVITY_TIMEOUT_SECONDS,
                    )
                    continue

                if not users:
                    continue

                threshold_days = settings.license_inactive_threshold_days
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)
                default_seat_price_usd = self._resolve_estimated_savings(
                    creds.connector_config
                )

                for user in users:
                    if not isinstance(user, dict):
                        stats["users_skipped_invalid"] += 1
                        logger.warning(
                            "license_governance_invalid_user_payload",
                            tenant_id=str(tenant_id),
                            connection_id=str(conn.id),
                            payload_type=type(user).__name__,
                        )
                        continue

                    # Skip suspended users (already deactivated)
                    if user.get("suspended"):
                        continue

                    # Safety check: skip admins
                    if user.get("is_admin"):
                        continue

                    user_id = self._normalize_user_id(user.get("user_id"))
                    user_email = self._normalize_user_email(user.get("email"))
                    if not user_id or not user_email:
                        stats["users_skipped_invalid"] += 1
                        logger.warning(
                            "license_governance_invalid_user_identity",
                            tenant_id=str(tenant_id),
                            connection_id=str(conn.id),
                            user_id_present=bool(user_id),
                            email_present=bool(user_email),
                        )
                        continue

                    last_active, parse_error = self._normalize_last_active(
                        user.get("last_active_at")
                    )
                    if parse_error:
                        stats["users_skipped_invalid"] += 1
                        logger.warning(
                            "license_governance_invalid_last_active",
                            tenant_id=str(tenant_id),
                            connection_id=str(conn.id),
                            user_id=user_id,
                            raw_last_active=repr(user.get("last_active_at")),
                        )
                        continue

                    # Determine if user should be flagged:
                    # - last_active is None → never logged in → flag as inactive
                    # - last_active < cutoff → exceeded threshold → flag as inactive
                    is_inactive = last_active is None or last_active < cutoff_date
                    if not is_inactive:
                        continue

                    stats["users_flagged"] += 1

                    # Duplicate-request guard
                    if await self._has_pending_request(tenant_id, user_id):
                        stats["duplicates_skipped"] += 1
                        continue

                    inactive_reason = (
                        f"User {user_email} never logged in."
                        if last_active is None
                        else f"User {user_email} inactive since {last_active.isoformat()}."
                    )

                    request = await self.remediation_service.create_request(
                        tenant_id=tenant_id,
                        user_id=SYSTEM_USER_ID,
                        resource_id=user_id,
                        resource_type="license_seat",
                        action=RemediationAction.RECLAIM_LICENSE_SEAT,
                        estimated_savings=default_seat_price_usd,
                        provider="license",
                        connection_id=conn.id,
                        confidence_score=1.0,
                        explainability_notes=inactive_reason,
                        parameters={
                            "email": user_email,
                            "last_active_at": last_active.isoformat() if last_active else None,
                            "vendor": conn.vendor,
                        }
                    )
                    stats["requests_created"] += 1
                    
                    # If auto-pilot is enabled, trigger execution (handles grace period)
                    if settings.auto_pilot_enabled:
                        try:
                            execution_result = await self.remediation_service.execute(
                                request.id, tenant_id
                            )
                            result_status = normalize_remediation_status(
                                execution_result.status
                            )
                            if result_status == RemediationStatus.COMPLETED.value:
                                stats["executions_completed"] += 1
                                from app.shared.core.notifications import (
                                    NotificationDispatcher,
                                )

                                await NotificationDispatcher.notify_license_reclamation(
                                    tenant_id=str(tenant_id),
                                    user_email=user_email,
                                    last_active_at=last_active or datetime.fromtimestamp(0, tz=timezone.utc),
                                    savings=float(default_seat_price_usd),
                                    grace_period_days=settings.license_reclaim_grace_period_days,
                                    request_id=str(request.id),
                                    db=self.db,
                                )
                                continue

                            if result_status == RemediationStatus.FAILED.value:
                                stats["executions_failed"] += 1
                                failure = parse_remediation_execution_error(
                                    getattr(execution_result, "execution_error", None)
                                )
                                logger.warning(
                                    "license_governance_execution_failed",
                                    tenant_id=str(tenant_id),
                                    connection_id=str(conn.id),
                                    request_id=str(request.id),
                                    reason=failure.reason,
                                    status_code=failure.status_code,
                                    error=failure.message,
                                )
                                continue

                            stats["executions_deferred"] += 1
                            logger.info(
                                "license_governance_execution_deferred",
                                tenant_id=str(tenant_id),
                                connection_id=str(conn.id),
                                request_id=str(request.id),
                                status=result_status or "unknown",
                            )
                        except Exception as e:
                            stats["executions_failed"] += 1
                            logger.error(
                                "license_governance_execution_error",
                                tenant_id=str(tenant_id),
                                connection_id=str(conn.id),
                                request_id=str(request.id),
                                error=str(e),
                            )
                            continue

            except (ExternalAPIError, httpx.HTTPError) as e:
                logger.error(
                    "license_governance_connection_api_failed",
                    tenant_id=str(tenant_id),
                    connection_id=str(conn.id),
                    error=str(e),
                )
                continue
            except SQLAlchemyError as e:
                logger.error(
                    "license_governance_connection_db_failed",
                    tenant_id=str(tenant_id),
                    connection_id=str(conn.id),
                    error=str(e),
                )
                continue
            except Exception as e:
                logger.error(
                    "license_governance_connection_unexpected_failed",
                    tenant_id=str(tenant_id),
                    connection_id=str(conn.id),
                    error=str(e),
                )
                continue

        logger.info("license_governance_completed", tenant_id=str(tenant_id), stats=stats)
        return {"status": "completed", "stats": stats}
