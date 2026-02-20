from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.domain.security.audit_log import (
    AuditEventType,
    AuditLog,
    AuditLogger,
)
from app.shared.core.connection_queries import CONNECTION_MODEL_PAIRS

logger = structlog.get_logger()


class BudgetHardCapService:
    """
    Enforces a tenant hard-cap by suspending connector activity.

    Safety guarantees:
    - Requires explicit approval for enforcement.
    - Captures a durable snapshot of prior connection states.
    - Writes immutable audit events for enforce/reverse actions.
    - Supports full rollback via reverse_hard_cap().
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _snapshot_key(provider: str) -> str:
        return f"{provider}_connections"

    @staticmethod
    def _coerce_uuid(value: Any) -> UUID | None:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _empty_snapshot() -> dict[str, list[dict[str, Any]]]:
        return {
            BudgetHardCapService._snapshot_key(provider): []
            for provider, _model in CONNECTION_MODEL_PAIRS
        }

    async def _capture_snapshot(self, tenant_id: UUID) -> dict[str, list[dict[str, Any]]]:
        snapshot = self._empty_snapshot()

        for provider, model in CONNECTION_MODEL_PAIRS:
            key = self._snapshot_key(provider)
            if hasattr(model, "status"):
                rows = await self.db.execute(
                    select(model.id, model.status).where(model.tenant_id == tenant_id)
                )
                snapshot[key] = [
                    {"id": str(row.id), "status": str(row.status or "pending")}
                    for row in rows.all()
                ]
                continue

            rows = await self.db.execute(
                select(model.id, model.is_active).where(model.tenant_id == tenant_id)
            )
            snapshot[key] = [
                {"id": str(row.id), "is_active": bool(row.is_active)}
                for row in rows.all()
            ]

        return snapshot

    async def _apply_enforcement(self, tenant_id: UUID) -> None:
        for _provider, model in CONNECTION_MODEL_PAIRS:
            if hasattr(model, "status"):
                await self.db.execute(
                    update(model)
                    .where(
                        model.tenant_id == tenant_id,
                        model.status != "suspended",
                    )
                    .values(status="suspended")
                )
                continue
            await self.db.execute(
                update(model)
                .where(model.tenant_id == tenant_id, model.is_active.is_(True))
                .values(is_active=False)
            )

    async def _restore_from_snapshot(
        self, tenant_id: UUID, snapshot: dict[str, Any]
    ) -> int:
        restored = 0

        for provider, model in CONNECTION_MODEL_PAIRS:
            key = self._snapshot_key(provider)
            for row in snapshot.get(key, []):
                if not isinstance(row, dict):
                    continue
                connection_id = self._coerce_uuid(row.get("id"))
                if connection_id is None:
                    continue
                if hasattr(model, "status"):
                    status = str(row.get("status") or "pending")
                    await self.db.execute(
                        update(model)
                        .where(model.tenant_id == tenant_id, model.id == connection_id)
                        .values(status=status)
                    )
                else:
                    is_active = self._coerce_bool(row.get("is_active"), default=False)
                    await self.db.execute(
                        update(model)
                        .where(model.tenant_id == tenant_id, model.id == connection_id)
                        .values(is_active=is_active)
                    )
                restored += 1

        return restored

    async def _load_latest_snapshot(self, tenant_id: UUID) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(AuditLog.details)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.event_type == AuditEventType.BUDGET_HARD_CAP_ENFORCED.value,
            )
            .order_by(desc(AuditLog.event_timestamp))
            .limit(1)
        )
        details = result.scalar_one_or_none()
        if not isinstance(details, dict):
            return None
        snapshot = details.get("snapshot")
        return snapshot if isinstance(snapshot, dict) else None

    async def _write_audit(
        self,
        *,
        tenant_id: UUID,
        event_type: AuditEventType,
        actor_id: UUID | str | None,
        details: dict[str, Any],
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        audit = AuditLogger(self.db, tenant_id)
        await audit.log(
            event_type=event_type,
            actor_id=actor_id,
            resource_type="tenant",
            resource_id=str(tenant_id),
            details=details,
            success=success,
            error_message=error_message,
        )

    async def enforce_hard_cap(
        self,
        tenant_id: UUID,
        *,
        approved: bool = False,
        actor_id: UUID | str | None = None,
        reason: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Suspend tenant connections after explicit operator approval.

        Returns the captured pre-enforcement snapshot for deterministic rollback.
        """
        if not approved:
            error_message = "Hard-cap enforcement requires explicit approval."
            logger.warning(
                "hard_cap_enforcement_blocked",
                tenant_id=str(tenant_id),
                reason=reason,
            )
            await self._write_audit(
                tenant_id=tenant_id,
                event_type=AuditEventType.BUDGET_HARD_CAP_ENFORCEMENT_BLOCKED,
                actor_id=actor_id,
                details={"reason": reason or "approval_missing"},
                success=False,
                error_message=error_message,
            )
            await self.db.commit()
            raise PermissionError(error_message)

        logger.warning(
            "enforcing_hard_cap",
            tenant_id=str(tenant_id),
            actor_id=str(actor_id) if actor_id else None,
        )

        try:
            snapshot = await self._capture_snapshot(tenant_id)
            await self._apply_enforcement(tenant_id)
            await self._write_audit(
                tenant_id=tenant_id,
                event_type=AuditEventType.BUDGET_HARD_CAP_ENFORCED,
                actor_id=actor_id,
                details={
                    "reason": reason or "budget_hard_cap_reached",
                    "snapshot": snapshot,
                },
            )
            await self.db.commit()
        except Exception:
            rollback = getattr(self.db, "rollback", None)
            if callable(rollback):
                await rollback()
            raise

        logger.info("hard_cap_enforcement_complete", tenant_id=str(tenant_id))
        return snapshot

    async def reverse_hard_cap(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID | str | None = None,
        reason: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> int:
        """
        Reverse a previous hard-cap enforcement and restore prior connection state.

        If no snapshot is provided, the latest enforced snapshot is loaded from audit logs.
        Returns the number of connection rows restored.
        """
        try:
            active_snapshot = snapshot or await self._load_latest_snapshot(tenant_id)
            if not isinstance(active_snapshot, dict):
                raise ValueError(
                    "No hard-cap snapshot available for tenant; cannot reverse."
                )

            restored = await self._restore_from_snapshot(tenant_id, active_snapshot)
            await self._write_audit(
                tenant_id=tenant_id,
                event_type=AuditEventType.BUDGET_HARD_CAP_REVERSED,
                actor_id=actor_id,
                details={
                    "reason": reason or "operator_reactivation",
                    "restored_connections": restored,
                },
            )
            await self.db.commit()
        except Exception:
            rollback = getattr(self.db, "rollback", None)
            if callable(rollback):
                await rollback()
            raise

        logger.info(
            "hard_cap_reversal_complete",
            tenant_id=str(tenant_id),
            restored_connections=restored,
        )
        return restored
