from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog
from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.domain.security.audit_log import AuditLog


def _details(row: Any) -> dict[str, Any]:
    details = getattr(row, "details", None)
    return details if isinstance(details, dict) else {}


def _base_evidence_item(row: Any) -> dict[str, Any]:
    return {
        "event_id": str(row.id),
        "run_id": row.correlation_id,
        "timestamp": row.event_timestamp.isoformat(),
        "success": bool(row.success),
        "actor_email": row.actor_email,
    }


async def collect_integration_evidence(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    event_types: Iterable[str],
    limit: int,
) -> list[dict[str, Any]]:
    event_type_values = [str(item) for item in event_types]
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type.in_(event_type_values))
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        details = _details(row)
        item = _base_evidence_item(row)
        item["event_type"] = row.event_type
        item["channel"] = str(details.get("channel", row.resource_id or "unknown"))
        item["status_code"] = details.get("status_code")
        item["message"] = details.get("result_message", row.error_message)
        items.append(item)
    return items


async def collect_payload_evidence(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    event_type: str,
    payload_key: str,
    limit: int,
    include_thresholds: bool = False,
) -> list[dict[str, Any]]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == event_type)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        details = _details(row)
        payload = details.get(payload_key)
        if not isinstance(payload, dict):
            continue
        item = _base_evidence_item(row)
        if include_thresholds:
            item["thresholds"] = details.get("thresholds", {})
        item[payload_key] = payload
        items.append(item)
    return items


async def collect_settings_snapshots(
    *, db: AsyncSession, tenant_id: UUID
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    notif = (
        await db.execute(
            select(NotificationSettings).where(NotificationSettings.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    notif_snapshot: dict[str, Any] = {
        "exists": bool(notif),
        "slack_enabled": bool(getattr(notif, "slack_enabled", True)) if notif else True,
        "slack_channel_override": getattr(notif, "slack_channel_override", None)
        if notif
        else None,
        "jira_enabled": bool(getattr(notif, "jira_enabled", False)) if notif else False,
        "jira_base_url": getattr(notif, "jira_base_url", None) if notif else None,
        "jira_email": getattr(notif, "jira_email", None) if notif else None,
        "jira_project_key": getattr(notif, "jira_project_key", None) if notif else None,
        "jira_issue_type": (getattr(notif, "jira_issue_type", None) or "Task")
        if notif
        else "Task",
        "has_jira_api_token": bool(getattr(notif, "jira_api_token", None))
        if notif
        else False,
        "teams_enabled": bool(getattr(notif, "teams_enabled", False)) if notif else False,
        "has_teams_webhook_url": bool(getattr(notif, "teams_webhook_url", None))
        if notif
        else False,
        "workflow_github_enabled": bool(
            getattr(notif, "workflow_github_enabled", False)
        )
        if notif
        else False,
        "workflow_github_owner": getattr(notif, "workflow_github_owner", None)
        if notif
        else None,
        "workflow_github_repo": getattr(notif, "workflow_github_repo", None)
        if notif
        else None,
        "workflow_github_workflow_id": getattr(
            notif, "workflow_github_workflow_id", None
        )
        if notif
        else None,
        "workflow_github_ref": (getattr(notif, "workflow_github_ref", None) or "main")
        if notif
        else "main",
        "workflow_has_github_token": bool(getattr(notif, "workflow_github_token", None))
        if notif
        else False,
        "workflow_gitlab_enabled": bool(
            getattr(notif, "workflow_gitlab_enabled", False)
        )
        if notif
        else False,
        "workflow_gitlab_base_url": (
            getattr(notif, "workflow_gitlab_base_url", None) or "https://gitlab.com"
        )
        if notif
        else "https://gitlab.com",
        "workflow_gitlab_project_id": getattr(notif, "workflow_gitlab_project_id", None)
        if notif
        else None,
        "workflow_gitlab_ref": (getattr(notif, "workflow_gitlab_ref", None) or "main")
        if notif
        else "main",
        "workflow_has_gitlab_trigger_token": bool(
            getattr(notif, "workflow_gitlab_trigger_token", None)
        )
        if notif
        else False,
        "workflow_webhook_enabled": bool(
            getattr(notif, "workflow_webhook_enabled", False)
        )
        if notif
        else False,
        "workflow_webhook_url": getattr(notif, "workflow_webhook_url", None)
        if notif
        else None,
        "workflow_has_webhook_bearer_token": bool(
            getattr(notif, "workflow_webhook_bearer_token", None)
        )
        if notif
        else False,
        "digest_schedule": getattr(notif, "digest_schedule", "daily")
        if notif
        else "daily",
        "digest_hour": int(getattr(notif, "digest_hour", 9)) if notif else 9,
        "digest_minute": int(getattr(notif, "digest_minute", 0)) if notif else 0,
        "alert_on_budget_warning": bool(getattr(notif, "alert_on_budget_warning", True))
        if notif
        else True,
        "alert_on_budget_exceeded": bool(getattr(notif, "alert_on_budget_exceeded", True))
        if notif
        else True,
        "alert_on_zombie_detected": bool(getattr(notif, "alert_on_zombie_detected", True))
        if notif
        else True,
    }

    remediation_settings = (
        await db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    remediation_snapshot: dict[str, Any] = {
        "exists": bool(remediation_settings),
        "auto_pilot_enabled": bool(
            getattr(remediation_settings, "auto_pilot_enabled", False)
        )
        if remediation_settings
        else False,
        "simulation_mode": bool(getattr(remediation_settings, "simulation_mode", True))
        if remediation_settings
        else True,
        "min_confidence_threshold": float(
            getattr(remediation_settings, "min_confidence_threshold", 0.95)
        )
        if remediation_settings
        else 0.95,
        "max_deletions_per_hour": int(
            getattr(remediation_settings, "max_deletions_per_hour", 10)
        )
        if remediation_settings
        else 10,
        "hard_cap_enabled": bool(getattr(remediation_settings, "hard_cap_enabled", False))
        if remediation_settings
        else False,
        "monthly_hard_cap_usd": float(
            getattr(remediation_settings, "monthly_hard_cap_usd", 0.0)
        )
        if remediation_settings
        else 0.0,
        "policy_enabled": bool(getattr(remediation_settings, "policy_enabled", True))
        if remediation_settings
        else True,
        "policy_block_production_destructive": bool(
            getattr(remediation_settings, "policy_block_production_destructive", True)
        )
        if remediation_settings
        else True,
        "policy_require_gpu_override": bool(
            getattr(remediation_settings, "policy_require_gpu_override", True)
        )
        if remediation_settings
        else True,
        "policy_low_confidence_warn_threshold": float(
            getattr(remediation_settings, "policy_low_confidence_warn_threshold", 0.90)
        )
        if remediation_settings
        else 0.90,
        "policy_violation_notify_slack": bool(
            getattr(remediation_settings, "policy_violation_notify_slack", True)
        )
        if remediation_settings
        else True,
        "policy_violation_notify_jira": bool(
            getattr(remediation_settings, "policy_violation_notify_jira", False)
        )
        if remediation_settings
        else False,
        "policy_escalation_required_role": str(
            getattr(remediation_settings, "policy_escalation_required_role", "owner")
        )
        if remediation_settings
        else "owner",
    }

    identity_settings = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    identity_snapshot: dict[str, Any] = {
        "exists": bool(identity_settings),
        "sso_enabled": bool(getattr(identity_settings, "sso_enabled", False))
        if identity_settings
        else False,
        "allowed_email_domains": list(
            getattr(identity_settings, "allowed_email_domains", []) or []
        )
        if identity_settings
        else [],
        "scim_enabled": bool(getattr(identity_settings, "scim_enabled", False))
        if identity_settings
        else False,
        "has_scim_token": bool(getattr(identity_settings, "scim_bearer_token", None))
        if identity_settings
        else False,
        "scim_last_rotated_at": identity_settings.scim_last_rotated_at.isoformat()
        if identity_settings and identity_settings.scim_last_rotated_at
        else None,
        "scim_group_mappings": list(
            getattr(identity_settings, "scim_group_mappings", []) or []
        )
        if identity_settings
        else [],
    }
    return notif_snapshot, remediation_snapshot, identity_snapshot


async def collect_carbon_factor_evidence(
    *, db: AsyncSession, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    factor_set_rows = (
        (
            await db.execute(
                select(CarbonFactorSet)
                .order_by(desc(CarbonFactorSet.created_at))
                .limit(int(limit))
            )
        )
        .scalars()
        .all()
    )
    carbon_factor_sets: list[dict[str, Any]] = []
    for factor_set_row in factor_set_rows:
        carbon_factor_sets.append(
            {
                "id": str(factor_set_row.id),
                "status": str(factor_set_row.status),
                "is_active": bool(factor_set_row.is_active),
                "factor_source": str(factor_set_row.factor_source),
                "factor_version": str(factor_set_row.factor_version),
                "factor_timestamp": factor_set_row.factor_timestamp.isoformat(),
                "methodology_version": str(factor_set_row.methodology_version),
                "factors_checksum_sha256": str(factor_set_row.factors_checksum_sha256),
                "created_at": factor_set_row.created_at.isoformat(),
                "activated_at": factor_set_row.activated_at.isoformat()
                if factor_set_row.activated_at
                else None,
                "deactivated_at": factor_set_row.deactivated_at.isoformat()
                if factor_set_row.deactivated_at
                else None,
                "created_by_user_id": str(factor_set_row.created_by_user_id)
                if factor_set_row.created_by_user_id
                else None,
                "payload": factor_set_row.payload
                if isinstance(factor_set_row.payload, dict)
                else {},
            }
        )

    factor_update_rows = (
        (
            await db.execute(
                select(CarbonFactorUpdateLog)
                .order_by(desc(CarbonFactorUpdateLog.recorded_at))
                .limit(int(limit))
            )
        )
        .scalars()
        .all()
    )
    carbon_factor_update_logs: list[dict[str, Any]] = []
    for factor_update_row in factor_update_rows:
        carbon_factor_update_logs.append(
            {
                "id": str(factor_update_row.id),
                "recorded_at": factor_update_row.recorded_at.isoformat(),
                "action": str(factor_update_row.action),
                "message": factor_update_row.message,
                "old_factor_set_id": str(factor_update_row.old_factor_set_id)
                if factor_update_row.old_factor_set_id
                else None,
                "new_factor_set_id": str(factor_update_row.new_factor_set_id)
                if factor_update_row.new_factor_set_id
                else None,
                "old_checksum_sha256": factor_update_row.old_checksum_sha256,
                "new_checksum_sha256": factor_update_row.new_checksum_sha256,
                "details": factor_update_row.details
                if isinstance(factor_update_row.details, dict)
                else {},
                "actor_user_id": str(factor_update_row.actor_user_id)
                if factor_update_row.actor_user_id
                else None,
            }
        )
    return carbon_factor_sets, carbon_factor_update_logs
